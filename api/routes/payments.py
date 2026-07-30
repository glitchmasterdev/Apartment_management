from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from api.models import PublicPaymentSubmit, TenantPaymentSubmit, PaymentApproveRequest, PaymentRejectRequest
from api.services.auth_middleware import get_current_user, require_role
from api.services.access import db_for, tenant_for_session, unit_for_staff, allowed_building_ids, require_building_access, fail_closed

router = APIRouter(prefix="/payments", tags=["Payments"])
STAFF=["landlord","caretaker"]

@router.post("")
def submit(req:TenantPaymentSubmit,user:dict=Depends(require_role(["tenant"]))):
    if req.amount <= 0: raise HTTPException(422,"Payment amount must be greater than zero.")
    if not str(req.mpesa_code).strip(): raise HTTPException(422,"Enter the payment reference.")
    db=db_for(user); tenant=tenant_for_session(db,user)
    try:
        record={"tenant_id":tenant["id"],"unit_id":tenant["unit_id"],"amount_paid":req.amount,"payment_date":req.payment_date or datetime.now(timezone.utc).isoformat(),"mpesa_code":str(req.mpesa_code).strip().upper()[:40],"tenant_message":str(req.notes or "")[:300],"status":"pending"}
        result=db.table("payments").insert(record).execute().data[0]
    except Exception as exc: fail_closed(exc,"payment_submit")
    return {"status":"success","message":"Payment record submitted for review.","payment":result}

@router.post("/public-submit")
def legacy_submit(req:PublicPaymentSubmit,user:dict=Depends(require_role(["tenant"]))):
    return submit(TenantPaymentSubmit(amount=req.amount_paid,mpesa_code=req.mpesa_code,notes=req.tenant_message),user)

@router.get("/me")
def mine(user:dict=Depends(require_role(["tenant"]))):
    try: return {"payments":db_for(user).table("payments").select("*").eq("tenant_id",user["id"]).order("payment_date",desc=True).execute().data}
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
def all_payments(building_id:str|None=None,user:dict=Depends(require_role(STAFF))):
    try: payments,_=_staff_payments(db_for(user),user,building_id); return {"payments":payments}
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

def _change(ids,status,user,reason=None):
    if not ids or len(ids)>100: raise HTTPException(422,"Select between 1 and 100 payments.")
    db=db_for(user); changed=0
    try:
        for payment_id in ids:
            rows=db.table("payments").select("unit_id").eq("id",payment_id).limit(1).execute().data
            if not rows: continue
            unit_for_staff(db,user,rows[0]["unit_id"])
            values={"status":status,"approved_by":user["id"],"approved_at":datetime.now(timezone.utc).isoformat()} if status=="approved" else {"status":"rejected","rejection_reason":reason[:500]}
            db.table("payments").update(values).eq("id",payment_id).execute(); changed+=1
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"payment_review")
    return {"status":"success",f"{status}_count":changed}

@router.post("/approve")
def approve(req:PaymentApproveRequest,user:dict=Depends(require_role(STAFF))): return _change(req.payment_ids,"approved",user)
@router.post("/reject")
def reject(req:PaymentRejectRequest,user:dict=Depends(require_role(STAFF))):
    if not req.reason.strip(): raise HTTPException(422,"Provide a reason for rejecting the payment.")
    return _change(req.payment_ids,"rejected",user,req.reason)
