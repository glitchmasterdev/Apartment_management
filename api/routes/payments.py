from fastapi import APIRouter, HTTPException, Depends
from api.models import PublicPaymentSubmit, TenantPaymentSubmit, PaymentApproveRequest, PaymentRejectRequest
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import require_role, get_current_user
from api.services.email import send_receipt_email, send_rejection_email, send_landlord_alert_email
from api.services.ledger import calculate_tenant_ledger
import uuid
from datetime import datetime

router = APIRouter(prefix="/payments", tags=["Payments"])

STAFF = ["landlord", "caretaker"]


@router.post("")
def submit_authenticated_payment(
    req: TenantPaymentSubmit,
    current_user: dict = Depends(get_current_user),
):
    db = get_supabase_client()
    tenant_id = req.tenant_id or current_user.get("id")
    unit_id = req.unit_id or current_user.get("unit_id")

    new_payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "unit_id": unit_id,
        "amount_paid": req.amount,
        "payment_date": req.payment_date or datetime.now().isoformat(),
        "mpesa_code": str(req.mpesa_code).strip().upper()[:20],
        "tenant_message": str(req.notes or "")[:300],
        "receipt_url": "",
        "status": "pending",
        "rejection_reason": None,
    }

    if hasattr(db, "payments"):
        db.payments.append(new_payment)
    else:
        try:
            db.table("payments").insert(new_payment).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to submit payment: {str(e)}")

    try:
        send_landlord_alert_email(
            landlord_email="landlord@nairobrentals.com",
            tenant_name=current_user.get("full_name", "Tenant"),
            unit_number="Unit",
            amount=req.amount,
        )
    except Exception:
        pass

    return {"status": "success", "message": "Payment submitted for approval.", "payment": new_payment}


@router.get("/pending")
def get_pending_payments(
    building_id: str = None,
    current_user: dict = Depends(require_role(STAFF)),
):
    db = get_supabase_client()
    try:
        payments = db.payments if hasattr(db, "payments") else db.table("payments").select("*").execute().data
        units = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
        tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load payments: {str(e)}")

    pending = [p for p in payments if p.get("status") == "pending"]
    results = []
    for p in pending:
        unit = next((u for u in units if u.get("id") == p.get("unit_id")), {})
        if building_id and unit.get("building_id") != building_id:
            continue
        tenant = next((t for t in tenants if t.get("id") == p.get("tenant_id")), {})
        p_copy = dict(p)
        p_copy["unit_number"] = unit.get("unit_number", "N/A")
        p_copy["tenant_name"] = tenant.get("full_name", "N/A")
        p_copy["phone_number"] = tenant.get("phone_number", "N/A")
        results.append(p_copy)

    return {"pending_payments": results}


@router.get("")
def get_all_payments(
    building_id: str = None,
    current_user: dict = Depends(require_role(STAFF)),
):
    db = get_supabase_client()
    try:
        payments = db.payments if hasattr(db, "payments") else db.table("payments").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load payments: {str(e)}")
    return {"payments": payments}


@router.post("/approve")
def approve_payments(
    req: PaymentApproveRequest,
    current_user: dict = Depends(require_role(STAFF)),
):
    db = get_supabase_client()
    try:
        payments = db.payments if hasattr(db, "payments") else db.table("payments").select("*").execute().data
        tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load data: {str(e)}")

    approved_count = 0
    for pid in req.payment_ids:
        payment = next((p for p in payments if p.get("id") == pid), None)
        if payment:
            payment["status"] = "approved"
            payment["approved_at"] = datetime.now().isoformat()
            approved_count += 1
            if not hasattr(db, "payments"):
                try:
                    db.table("payments").update({"status": "approved", "approved_at": payment["approved_at"]}).eq("id", pid).execute()
                except Exception:
                    pass
            tenant = next((t for t in tenants if t.get("id") == payment.get("tenant_id")), {})
            if tenant:
                t_payments = [p for p in payments if p.get("tenant_id") == tenant.get("id") and p.get("status") == "approved"]
                ledger = calculate_tenant_ledger(tenant.get("monthly_rent", 0), t_payments)
                try:
                    send_receipt_email(
                        tenant_email=tenant.get("email"),
                        tenant_name=tenant.get("full_name"),
                        amount=payment.get("amount_paid"),
                        period=datetime.now().strftime("%B %Y"),
                        balance=ledger.get("balance", 0.0),
                    )
                except Exception:
                    pass

    return {"status": "success", "approved_count": approved_count}


@router.post("/reject")
def reject_payments(
    req: PaymentRejectRequest,
    current_user: dict = Depends(require_role(STAFF)),
):
    db = get_supabase_client()
    try:
        payments = db.payments if hasattr(db, "payments") else db.table("payments").select("*").execute().data
        tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load data: {str(e)}")

    rejected_count = 0
    for pid in req.payment_ids:
        payment = next((p for p in payments if p.get("id") == pid), None)
        if payment:
            payment["status"] = "rejected"
            payment["rejection_reason"] = req.reason
            rejected_count += 1
            if not hasattr(db, "payments"):
                try:
                    db.table("payments").update({"status": "rejected", "rejection_reason": req.reason}).eq("id", pid).execute()
                except Exception:
                    pass
            tenant = next((t for t in tenants if t.get("id") == payment.get("tenant_id")), {})
            if tenant:
                try:
                    send_rejection_email(
                        tenant_email=tenant.get("email"),
                        tenant_name=tenant.get("full_name"),
                        reason=req.reason,
                    )
                except Exception:
                    pass

    return {"status": "success", "rejected_count": rejected_count}


@router.post("/public-submit")
def public_submit_payment(req: PublicPaymentSubmit):
    """PUBLIC ENDPOINT — tenants submit M-Pesa proof without logging in."""
    db = get_supabase_client()
    try:
        units = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
        tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

    unit = next((u for u in units if str(u.get("unit_number")).upper() == str(req.unit_number).upper()), None)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit number not found. Please double check your unit number.")

    tenant = next((t for t in tenants if t.get("unit_id") == unit.get("id") and t.get("is_active")), None)
    if not tenant:
        raise HTTPException(status_code=400, detail="No active tenant found for this unit. Please contact management.")

    new_payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant.get("id"),
        "unit_id": unit.get("id"),
        "amount_paid": req.amount_paid,
        "payment_date": datetime.now().isoformat(),
        "mpesa_code": str(req.mpesa_code).upper()[:20],
        "tenant_message": str(req.tenant_message or "")[:300],
        "receipt_url": req.receipt_photo,
        "status": "pending",
        "rejection_reason": None,
    }

    if hasattr(db, "payments"):
        db.payments.append(new_payment)
    else:
        try:
            db.table("payments").insert(new_payment).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to submit payment: {str(e)}")

    try:
        send_landlord_alert_email(
            landlord_email="landlord@nairobrentals.com",
            tenant_name=tenant.get("full_name"),
            unit_number=req.unit_number,
            amount=req.amount_paid,
        )
    except Exception:
        pass

    return {"status": "success", "message": "Payment proof submitted. You will receive an email receipt once approved."}
