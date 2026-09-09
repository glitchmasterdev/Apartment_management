from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from api.models import PublicPaymentSubmit, TenantPaymentSubmit, PaymentApproveRequest, PaymentRejectRequest, STKPushRequest
from api.config import settings
from api.services.auth_middleware import get_current_user, require_role
from api.services.access import db_for, tenant_for_session, unit_for_staff, allowed_building_ids, require_building_access, fail_closed
from api.services.email import send_payment_confirmation_email
from api.services.mpesa import configured as mpesa_configured, initiate_stk_push, normalise_kenyan_phone

router = APIRouter(prefix="/payments", tags=["Payments"])
STAFF=["landlord","caretaker"]


def _audit(db, actor: dict, action: str, entity_type: str, entity_id: str, details: dict | None = None) -> None:
    """Best-effort audit trail; a missing legacy table never breaks payment safety."""
    try:
        db.table("audit_logs").insert({"actor_id": actor.get("id"), "actor_role": actor.get("role"), "action": action,
            "entity_type": entity_type, "entity_id": entity_id, "details": details or {}}).execute()
    except Exception:
        pass


def _validate_payment_amount(amount: float, tenant: dict) -> None:
    """Prevent one payment submission from exceeding the tenant's monthly rent."""
    monthly_rent = float(tenant.get("monthly_rent") or 0)
    if monthly_rent <= 0:
        raise HTTPException(422, "Your monthly rent is not configured. Contact your landlord before submitting a payment.")
    if amount > monthly_rent:
        raise HTTPException(
            422,
            f"Payment cannot exceed your monthly rent of KES {monthly_rent:,.0f}.",
        )


def _approval_profile_id(db, user: dict) -> str:
    """Resolve the profile foreign key used by payment approvals.

    Legacy landlord sessions use an ID from the landlords table, while
    payments.approved_by references profiles.id. Reuse the one-time profile
    bridge used by property creation so approval does not fail after a tenant
    submits an otherwise valid payment.
    """
    if user.get("role") == "landlord":
        from api.routes.buildings import _ensure_landlord_profile
        return _ensure_landlord_profile(db, user)
    try:
        rows = db.table("profiles").select("id").eq("id", user["id"]).limit(1).execute().data
        if rows:
            return rows[0]["id"]
    except Exception:
        pass
    raise HTTPException(409, detail="The caretaker profile is not configured for payment approvals.")

@router.post("")
def submit(req:TenantPaymentSubmit,user:dict=Depends(require_role(["tenant"]))):
    """Store a tenant's payment-message proof without treating it as payment."""
    if req.amount <= 0: raise HTTPException(422, "Payment amount must be greater than zero.")
    message = str(req.transaction_message or "").strip()
    if len(message) < 20 or len(message) > 2000:
        raise HTTPException(422, "Paste the complete transaction message (20 to 2,000 characters).")
    db = db_for(user); tenant = tenant_for_session(db, user); _validate_payment_amount(req.amount, tenant)
    try:
        record = db.table("payments").insert({
            "tenant_id": tenant["id"], "unit_id": tenant["unit_id"], "amount_paid": req.amount,
            "payment_date": datetime.now(timezone.utc).isoformat(), "mpesa_code": None,
            "tenant_message": message, "status": "pending", "verification_status": "unverified_message",
            "mpesa_phone_number": str(req.phone_number or "")[:20],
        }).execute().data[0]
        return {"status": "pending_verification", "payment_id": record["id"], "message": "Message received and flagged as unverified. Safaricom confirmation is required before rent is credited."}
    except Exception as exc: fail_closed(exc, "submit_payment_message")


@router.post("/stk-push")
def start_stk_push(req: STKPushRequest, user: dict = Depends(require_role(["tenant"]))):
    """Ask Safaricom to collect rent; no tenant-provided receipt is trusted."""
    if req.amount <= 0:
        raise HTTPException(422, "Payment amount must be greater than zero.")
    if not mpesa_configured():
        raise HTTPException(503, "M-Pesa payments are not configured yet. Contact your landlord.")
    db = db_for(user)
    tenant = tenant_for_session(db, user)
    _validate_payment_amount(req.amount, tenant)
    try:
        phone = normalise_kenyan_phone(req.phone_number or tenant.get("phone_number"))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    account_reference = tenant.get("account_number") or f"TENANT-{tenant['id'][:8]}"
    try:
        safaricom_response = initiate_stk_push(phone, req.amount, account_reference, req.notes or "Rent payment")
        record = {
            "tenant_id": tenant["id"],
            "unit_id": tenant["unit_id"],
            "amount_paid": req.amount,
            "payment_date": datetime.now(timezone.utc).isoformat(),
            "mpesa_code": None,
            "tenant_message": str(req.notes or "")[:300],
            "status": "initiated",
            "mpesa_checkout_request_id": safaricom_response["CheckoutRequestID"],
            "mpesa_merchant_request_id": safaricom_response.get("MerchantRequestID"),
            "mpesa_phone_number": phone,
        }
        payment = db.table("payments").insert(record).execute().data[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Could not start the M-Pesa prompt. Please try again.") from exc
    return {
        "status": "initiated",
        "message": "Check your phone and enter your M-Pesa PIN to complete the payment.",
        "checkout_request_id": safaricom_response["CheckoutRequestID"],
        "payment_id": payment["id"],
    }


def _callback_metadata(callback: dict) -> dict:
    items = callback.get("CallbackMetadata", {}).get("Item", [])
    return {item.get("Name"): item.get("Value") for item in items if item.get("Name")}


def _mpesa_transaction_time(value, fallback: str) -> str:
    try:
        return datetime.strptime(str(value), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return fallback


@router.post("/mpesa/stk-callback")
async def stk_callback(request: Request, token: str = Query(default="")):
    """Safaricom's server-to-server confirmation. This is the payment authority."""
    if not settings.MPESA_CALLBACK_SECRET or token != settings.MPESA_CALLBACK_SECRET:
        raise HTTPException(401, "Invalid callback token.")
    try:
        callback = (await request.json()).get("Body", {}).get("stkCallback", {})
        checkout_id = callback.get("CheckoutRequestID")
        if not checkout_id:
            raise ValueError("Missing CheckoutRequestID")
        db = db_for({})
        rows = db.table("payments").select("*").eq("mpesa_checkout_request_id", checkout_id).limit(1).execute().data
        # A retry from Safaricom must be harmless and must never create a payment.
        if not rows:
            return {"ResultCode": 0, "ResultDesc": "Accepted"}
        payment = rows[0]
        if payment.get("status") == "approved":
            return {"ResultCode": 0, "ResultDesc": "Accepted"}
        result_code = int(callback.get("ResultCode", 1))
        if result_code != 0:
            db.table("payments").update({
                "status": "failed",
                "rejection_reason": str(callback.get("ResultDesc") or "M-Pesa payment was not completed.")[:500],
                "mpesa_callback_payload": callback,
            }).eq("id", payment["id"]).execute()
            return {"ResultCode": 0, "ResultDesc": "Accepted"}
        metadata = _callback_metadata(callback)
        receipt = str(metadata.get("MpesaReceiptNumber") or "").strip().upper()
        amount = float(metadata.get("Amount") or 0)
        phone = str(metadata.get("PhoneNumber") or "")
        if (not receipt or abs(amount - float(payment["amount_paid"])) > 0.01
                or phone != str(payment.get("mpesa_phone_number") or "")):
            db.table("payments").update({
                "status": "failed",
                "rejection_reason": "Safaricom callback did not match the requested payment.",
                "mpesa_callback_payload": callback,
            }).eq("id", payment["id"]).execute()
            return {"ResultCode": 0, "ResultDesc": "Accepted"}
        db.table("payments").update({
            "status": "approved",
            "verification_status": "stk_confirmed",
            "mpesa_code": receipt,
            "payment_date": _mpesa_transaction_time(metadata.get("TransactionDate"), payment["payment_date"]),
            "mpesa_callback_payload": callback,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", payment["id"]).execute()
        _audit(db, {"id": "safaricom", "role": "system"}, "payment_confirmed", "payment", payment["id"], {"source": "stk"})
    except Exception:
        # Return a controlled error so Safaricom retries; do not create any
        # payment from an incomplete or malformed callback.
        raise HTTPException(500, "Unable to process M-Pesa callback.")
    return {"ResultCode": 0, "ResultDesc": "Accepted"}

@router.post("/public-submit")
def legacy_submit(req:PublicPaymentSubmit,user:dict=Depends(require_role(["tenant"]))):
    return submit(TenantPaymentSubmit(amount=req.amount_paid, transaction_message=req.tenant_message or req.mpesa_code, phone_number=req.phone_number), user)


@router.post("/mpesa/c2b/confirmation")
async def c2b_confirmation(request: Request, token: str = Query(default="")):
    """Safaricom's authoritative PayBill/Buy Goods confirmation callback."""
    if not settings.MPESA_CALLBACK_SECRET or token != settings.MPESA_CALLBACK_SECRET:
        raise HTTPException(401, "Invalid callback token.")
    try:
        data = await request.json()
        receipt = str(data.get("TransID") or "").strip().upper()
        amount = float(data.get("TransAmount") or 0)
        reference = str(data.get("BillRefNumber") or "").strip()
        phone = str(data.get("MSISDN") or "")
        if not receipt or amount <= 0: raise ValueError("Missing Safaricom transaction details")
        db = db_for({})
        if db.table("payments").select("id").eq("mpesa_code", receipt).limit(1).execute().data:
            return {"ResultCode": 0, "ResultDesc": "Accepted"}
        tenants = db.table("tenants").select("id,unit_id,account_number,monthly_rent").eq("account_number", reference).limit(1).execute().data
        if not tenants:
            return {"ResultCode": 0, "ResultDesc": "Accepted for review"}
        tenant = tenants[0]
        saved = db.table("payments").insert({
            "tenant_id": tenant["id"], "unit_id": tenant["unit_id"], "amount_paid": amount,
            "payment_date": datetime.now(timezone.utc).isoformat(), "mpesa_code": receipt,
            "tenant_message": "Confirmed directly by Safaricom C2B callback.", "status": "approved",
            "verification_status": "safaricom_confirmed", "mpesa_phone_number": phone,
            "approved_at": datetime.now(timezone.utc).isoformat(), "mpesa_callback_payload": data,
        }).execute().data[0]
        _audit(db, {"id": "safaricom", "role": "system"}, "payment_confirmed", "payment", saved["id"], {"source": "c2b"})
    except Exception:
        raise HTTPException(500, "Unable to process M-Pesa confirmation.")
    return {"ResultCode": 0, "ResultDesc": "Accepted"}

@router.get("/me")
def mine(user:dict=Depends(require_role(["tenant"]))):
    try:
        records = db_for(user).table("payments").select("*").eq("tenant_id",user["id"]).order("payment_date",desc=True).execute().data
        if any(item.get("tenant_id") != user["id"] for item in records):
            raise HTTPException(403, "Payment history isolation check failed.")
        return {"payments":records}
    except Exception as exc: fail_closed(exc,"payment_history")

def _staff_payments(db,user,building_id=None,status=None):
    if building_id: require_building_access(db,user,building_id); buildings=[building_id]
    else: buildings=list(allowed_building_ids(db,user))
    units=db.table("units").select("id,building_id,unit_number").in_("building_id",buildings).execute().data if buildings else []
    ids=[u["id"] for u in units]
    query=db.table("payments").select("*").in_("unit_id",ids) if ids else None
    if status and query: query=query.eq("status",status)
    return (query.execute().data if query else []), units

@router.get("")
def all_payments(building_id:str|None=None, status:str|None=None, month:str|None=None, tenant_id:str|None=None, user:dict=Depends(require_role(STAFF))):
    try:
        payments,_ = _staff_payments(db_for(user),user,building_id,status)
        if month: payments = [p for p in payments if str(p.get("payment_date") or "").startswith(month)]
        if tenant_id: payments = [p for p in payments if str(p.get("tenant_id")) == tenant_id]
        return {"payments":payments}
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"payments_list")

@router.get("/pending")
def pending(building_id:str|None=None,user:dict=Depends(require_role(STAFF))):
    db=db_for(user)
    try:
        payments,units=_staff_payments(db,user,building_id,"pending"); tenants=db.table("tenants").select("id,full_name,phone_number").in_("id",[p["tenant_id"] for p in payments]).execute().data if payments else []
        by_unit={u["id"]:u for u in units}; by_tenant={t["id"]:t for t in tenants}
        return {"pending_payments":[{**p,"unit_number":by_unit.get(p["unit_id"],{}).get("unit_number",""),"tenant_name":by_tenant.get(p["tenant_id"],{}).get("full_name",""),"phone_number":by_tenant.get(p["tenant_id"],{}).get("phone_number","")} for p in payments]}
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"pending_payments")


@router.post("/follow-ups")
def record_follow_up(payload: dict, user: dict = Depends(require_role(STAFF))):
    """Record a staff arrears follow-up without creating a payment."""
    tenant_id = str(payload.get("tenant_id") or "")
    note = str(payload.get("note") or "").strip()
    promise_date = str(payload.get("promise_to_pay_date") or "").strip() or None
    if not tenant_id or not note or len(note) > 1000:
        raise HTTPException(422, "Provide a tenant and a follow-up note of up to 1,000 characters.")
    db = db_for(user)
    try:
        tenant = db.table("tenants").select("unit_id").eq("id", tenant_id).limit(1).execute().data
        if not tenant: raise HTTPException(404, "Tenant not found.")
        unit_for_staff(db, user, tenant[0]["unit_id"])
        saved = db.table("payment_follow_ups").insert({"tenant_id": tenant_id, "unit_id": tenant[0]["unit_id"], "staff_id": user["id"], "note": note, "promise_to_pay_date": promise_date}).execute().data[0]
        _audit(db, user, "arrears_follow_up", "tenant", tenant_id, {"promise_to_pay_date": promise_date})
        return {"status": "success", "follow_up": saved}
    except HTTPException: raise
    except Exception as exc: fail_closed(exc, "arrears_follow_up")

def _change(ids,status,user,reason=None):
    if not ids or len(ids)>100: raise HTTPException(422,"Select between 1 and 100 payments.")
    db=db_for(user); changed=0
    try:
        approver_profile_id = _approval_profile_id(db, user) if status == "approved" else None
        for payment_id in ids:
            rows=db.table("payments").select("unit_id,verification_status").eq("id",payment_id).limit(1).execute().data
            if not rows: continue
            if status == "approved" and rows[0].get("verification_status") in ("unverified_message", "manual_review"):
                raise HTTPException(409, "Unverified payment messages cannot be approved. Wait for Safaricom confirmation or reject the message.")
            unit_for_staff(db,user,rows[0]["unit_id"])
            values={"status":status,"approved_by":approver_profile_id,"approved_at":datetime.now(timezone.utc).isoformat()} if status=="approved" else {"status":"rejected","rejection_reason":reason[:500]}
            db.table("payments").update(values).eq("id",payment_id).execute(); _audit(db, user, f"payment_{status}", "payment", payment_id, {"reason": reason} if reason else {}); changed+=1
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"payment_review")
    return {"status":"success",f"{status}_count":changed}

@router.post("/approve")
def approve(req:PaymentApproveRequest, user:dict=Depends(require_role(["landlord"]))):
    return _change(req.payment_ids, "approved", user)
@router.post("/reject")
def reject(req:PaymentRejectRequest,user:dict=Depends(require_role(["landlord"]))):
    if not req.reason.strip(): raise HTTPException(422,"Provide a reason for rejecting the payment.")
    return _change(req.payment_ids,"rejected",user,req.reason)

@router.delete("/{payment_id}")
def delete_rejected_payment(payment_id: str, user: dict = Depends(require_role(["tenant"]))):
    db = db_for(user)
    try:
        payment = db.table("payments").select("tenant_id, status").eq("id", payment_id).execute().data
        if not payment:
            raise HTTPException(404, "Payment not found.")
        payment = payment[0]
        if payment["tenant_id"] != user["id"]:
            raise HTTPException(403, "Not authorized to delete this payment.")
        if payment["status"] != "rejected":
            raise HTTPException(400, "Only rejected payments can be deleted.")
        
        db.table("payments").delete().eq("id", payment_id).execute()
        return {"status": "success", "message": "Rejected payment deleted."}
    except HTTPException:
        raise
    except Exception as exc:
        fail_closed(exc, "delete_payment")
