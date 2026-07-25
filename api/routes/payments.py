from fastapi import APIRouter, HTTPException
from api.models import PublicPaymentSubmit, PaymentApproveRequest, PaymentRejectRequest
from api.services.supabase_client import get_supabase_client
from api.services.email import send_receipt_email, send_rejection_email, send_landlord_alert_email
from api.services.ledger import calculate_tenant_ledger
import uuid
from datetime import datetime

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.get("/pending")
def get_pending_payments(building_id: str = None):
    db = get_supabase_client()
    payments = db.payments if hasattr(db, "payments") else db.table("payments").select("*").execute().data
    units = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
    tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data

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

@router.post("/approve")
def approve_payments(req: PaymentApproveRequest):
    db = get_supabase_client()
    payments = db.payments if hasattr(db, "payments") else db.table("payments").select("*").execute().data
    tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data

    approved_count = 0
    for pid in req.payment_ids:
        payment = next((p for p in payments if p.get("id") == pid), None)
        if payment:
            payment["status"] = "approved"
            payment["approved_at"] = datetime.now().isoformat()
            approved_count += 1

            # Dispatch email receipt to tenant
            tenant = next((t for t in tenants if t.get("id") == payment.get("tenant_id")), {})
            if tenant:
                t_payments = [p for p in payments if p.get("tenant_id") == tenant.get("id") and p.get("status") == "approved"]
                ledger = calculate_tenant_ledger(tenant.get("monthly_rent", 0), t_payments)
                send_receipt_email(
                    tenant_email=tenant.get("email"),
                    tenant_name=tenant.get("full_name"),
                    amount=payment.get("amount_paid"),
                    period=datetime.now().strftime("%B %Y"),
                    balance=ledger.get("balance", 0.0)
                )

    return {"status": "success", "approved_count": approved_count}

@router.post("/reject")
def reject_payments(req: PaymentRejectRequest):
    db = get_supabase_client()
    payments = db.payments if hasattr(db, "payments") else db.table("payments").select("*").execute().data
    tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data

    rejected_count = 0
    for pid in req.payment_ids:
        payment = next((p for p in payments if p.get("id") == pid), None)
        if payment:
            payment["status"] = "rejected"
            payment["rejection_reason"] = req.reason
            rejected_count += 1

            tenant = next((t for t in tenants if t.get("id") == payment.get("tenant_id")), {})
            if tenant:
                send_rejection_email(
                    tenant_email=tenant.get("email"),
                    tenant_name=tenant.get("full_name"),
                    reason=req.reason
                )

    return {"status": "success", "rejected_count": rejected_count}

@router.post("/public-submit")
def public_submit_payment(req: PublicPaymentSubmit):
    """PUBLIC ENDPOINT - NO AUTH REQUIRED for tenants to submit M-Pesa proof."""
    db = get_supabase_client()
    units = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
    tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data

    unit = next((u for u in units if str(u.get("unit_number")).upper() == str(req.unit_number).upper()), None)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit number not found. Please double check your unit number.")

    tenant = next((t for t in tenants if t.get("unit_id") == unit.get("id") and t.get("is_active")), None)
    if not tenant:
        raise HTTPException(
            status_code=400, 
            detail="Cannot submit payment: No active tenant is registered for this unit. Please contact management."
        )
    tenant_id = tenant.get("id")
    tenant_name = tenant.get("full_name")

    new_payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "unit_id": unit.get("id"),
        "amount_paid": req.amount_paid,
        "payment_date": datetime.now().isoformat(),
        "mpesa_code": req.mpesa_code.upper(),
        "tenant_message": req.tenant_message,
        "receipt_url": req.receipt_photo,
        "status": "pending",
        "rejection_reason": None
    }

    if hasattr(db, "payments"):
        db.payments.append(new_payment)
    else:
        db.table("payments").insert(new_payment).execute()

    # Trigger email alert to landlord
    send_landlord_alert_email(
        landlord_email="landlord@nairobrentals.com",
        tenant_name=tenant_name,
        unit_number=req.unit_number,
        amount=req.amount_paid
    )

    return {
        "status": "success",
        "message": "Payment proof submitted successfully. You will receive an email receipt once approved."
    }
