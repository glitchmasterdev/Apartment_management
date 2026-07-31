"""Scoped maintenance, announcements, leases, privacy and landlord settings APIs."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from api.services.auth_middleware import get_current_user, require_role
from api.services.access import db_for, tenant_for_session, unit_for_staff, require_building_access, fail_closed

router = APIRouter(prefix="", tags=["Property features"])
STAFF = ["landlord", "caretaker"]


def _owned_tenant(db, user, tenant_id):
    rows = db.table("tenants").select("*").eq("id", tenant_id).limit(1).execute().data
    if not rows: raise HTTPException(404, "Tenant not found.")
    unit_for_staff(db, user, rows[0]["unit_id"])
    return rows[0]


@router.get("/tenant/me")
def tenant_me(user: dict = Depends(require_role(["tenant"]))):
    tenant = tenant_for_session(db_for(user), user)
    return {"tenant": {k:v for k,v in tenant.items() if k not in {"password", "password_hash"}}}


@router.get("/payment-status")
def payment_status(building_id: str | None = None, user: dict = Depends(require_role(STAFF))):
    db = db_for(user)
    try:
        allowed = []
        if building_id:
            require_building_access(db, user, building_id); allowed = [building_id]
        else:
            from api.services.access import allowed_building_ids
            allowed = list(allowed_building_ids(db, user))
        units = db.table("units").select("id,building_id,unit_number,rent_amount").in_("building_id", allowed).execute().data if allowed else []
        unit_ids = [x["id"] for x in units]
        tenants = db.table("tenants").select("*").in_("unit_id", unit_ids).eq("is_active", True).execute().data if unit_ids else []
        payments = db.table("payments").select("tenant_id,amount_paid,payment_date,status").in_("unit_id", unit_ids).eq("status", "approved").execute().data if unit_ids else []
        settings = db.table("landlord_settings").select("rent_due_day,late_fee_amount").eq("landlord_id", user.get("id")).limit(1).execute().data
        due_day = (settings[0]["rent_due_day"] if settings else 5)
        today = date.today()
        period = today.strftime("%Y-%m")
        output=[]
        for tenant in tenants:
            paid=sum(float(p.get("amount_paid") or 0) for p in payments if p["tenant_id"] == tenant["id"] and str(p.get("payment_date", "")).startswith(period))
            due=float(tenant.get("monthly_rent") or 0); outstanding=max(0, due-paid)
            state="paid" if outstanding == 0 else ("overdue" if today.day > due_day else "unpaid")
            output.append({"tenant_id": tenant["id"], "tenant_name": tenant["full_name"], "unit_number": next((u["unit_number"] for u in units if u["id"]==tenant["unit_id"]), ""), "due":due,"paid":paid,"outstanding":outstanding,"status":state,"due_day":due_day})
        return {"tenants": output}
    except HTTPException: raise
    except Exception as exc: fail_closed(exc, "payment_status")


@router.get("/landlord/settings")
def get_landlord_settings(user: dict = Depends(require_role(["landlord"]))):
    db=db_for(user)
    try:
        rows=db.table("landlord_settings").select("*").eq("landlord_id",user["id"]).limit(1).execute().data
        return {"settings": rows[0] if rows else {"rent_due_day":5,"reminder_days_before":3,"reminder_interval_days":1,"late_fee_amount":0,"notification_email":"","payment_instructions":"","bank_details":"","till_number":""}, "email_scheduling_active": False}
    except Exception as exc: fail_closed(exc,"get_landlord_settings")


@router.put("/landlord/settings")
def save_landlord_settings(payload: dict, user: dict = Depends(require_role(["landlord"]))):
    allowed={k:payload[k] for k in ("rent_due_day","reminder_days_before","reminder_interval_days","late_fee_amount","notification_email","payment_instructions","bank_details","till_number") if k in payload}
    if not 1 <= int(allowed.get("rent_due_day",5)) <= 28: raise HTTPException(422,"Rent due day must be between 1 and 28.")
    if float(allowed.get("late_fee_amount",0)) < 0: raise HTTPException(422,"Late fee cannot be negative.")
    try:
        db_for(user).table("landlord_settings").upsert({"landlord_id":user["id"],**allowed}).execute()
    except Exception as exc: fail_closed(exc,"save_landlord_settings")
    return {"status":"success","message":"Settings saved. Email scheduling is not enabled by this application."}


@router.get("/maintenance")
def maintenance(user: dict = Depends(get_current_user)):
    db=db_for(user)
    try:
        if user.get("role")=="tenant":
            return {"requests":db.table("maintenance_requests").select("*").eq("tenant_id",user["id"]).execute().data}
        if user.get("role") in STAFF:
            from api.services.access import allowed_building_ids
            units=db.table("units").select("id").in_("building_id",list(allowed_building_ids(db,user))).execute().data
            return {"requests":db.table("maintenance_requests").select("*").in_("unit_id",[u["id"] for u in units]).execute().data if units else []}
        raise HTTPException(403,"Access denied.")
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"maintenance_list")


@router.post("/maintenance")
def create_maintenance(payload: dict, user: dict = Depends(require_role(["tenant"]))):
    tenant=tenant_for_session(db_for(user),user)
    title=str(payload.get("title") or payload.get("category") or "Other").strip(); description=str(payload.get("description","")).strip(); photo_path=payload.get("photo_path")
    urgency=str(payload.get("urgency", "Routine")).strip().lower()
    if not title or len(title)>120: raise HTTPException(422,"Provide a maintenance title of at most 120 characters.")
    if len(description)<10 or len(description)>4000: raise HTTPException(422,"Describe the issue in 10 to 4,000 characters.")
    if photo_path and not str(photo_path).startswith(f"maintenance/{user['id']}/"): raise HTTPException(422,"Photo path is invalid.")
    if urgency not in {"routine", "urgent", "emergency"}: raise HTTPException(422,"Urgency must be routine, urgent, or emergency.")
    try: db_for(user).table("maintenance_requests").insert({"tenant_id":user["id"],"unit_id":tenant["unit_id"],"title":title,"category":title,"description":description,"urgency":urgency,"photo_path":photo_path,"status":"open"}).execute()
    except Exception as exc: fail_closed(exc,"maintenance_create")
    return {"status":"success","message":"Maintenance request submitted."}


@router.patch("/maintenance/{request_id}")
def update_maintenance(request_id:str,payload:dict,user:dict=Depends(require_role(STAFF))):
    status=payload.get("status"); assignee=str(payload.get("assignee_name","")).strip()
    if status not in {"open","in_progress","closed"}: raise HTTPException(422,"Status must be open, in progress, or closed.")
    db=db_for(user)
    try:
        item=db.table("maintenance_requests").select("unit_id").eq("id",request_id).limit(1).execute().data
        if not item: raise HTTPException(404,"Maintenance request not found.")
        unit_for_staff(db,user,item[0]["unit_id"])
        db.table("maintenance_requests").update({"status":status,"assignee_name":assignee[:120]}).eq("id",request_id).execute()
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"maintenance_update")
    return {"status":"success"}


@router.get("/announcements")
def list_announcements(user: dict = Depends(get_current_user)):
    db=db_for(user)
    try:
        if user.get("role") == "tenant":
            tenant=tenant_for_session(db,user)
            unit=db.table("units").select("building_id").eq("id",tenant["unit_id"]).single().execute().data
            rows=db.table("announcements").select("*").eq("building_id",unit["building_id"]).execute().data
            return {"announcements":[r for r in rows if not r.get("audience_tenant_ids") or user["id"] in r["audience_tenant_ids"]]}
        from api.services.access import allowed_building_ids
        return {"announcements":db.table("announcements").select("*").in_("building_id",list(allowed_building_ids(db,user))).execute().data}
    except Exception as exc: fail_closed(exc,"announcements_list")


@router.post("/announcements")
def create_announcement(payload:dict,user:dict=Depends(require_role(["landlord"]))):
    title=str(payload.get("title","")).strip(); body=str(payload.get("body","")).strip(); building_id=payload.get("building_id"); audience=payload.get("audience_tenant_ids") or []
    if not title or len(title)>160: raise HTTPException(422,"Title is required and must be at most 160 characters.")
    if not body or len(body)>5000: raise HTTPException(422,"Announcement text is required and must be at most 5,000 characters.")
    if not isinstance(audience,list): raise HTTPException(422,"Selected tenants must be a list.")
    db=db_for(user)
    try:
        require_building_access(db,user,building_id)
        for tenant_id in audience: _owned_tenant(db,user,tenant_id)
        db.table("announcements").insert({"landlord_id":user["id"],"building_id":building_id,"title":title,"body":body,"audience_tenant_ids":audience or None}).execute()
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"announcement_create")
    return {"status":"success"}


@router.get("/leases")
def list_leases(user:dict=Depends(get_current_user)):
    db=db_for(user)
    try:
        if user.get("role")=="tenant": return {"leases":db.table("leases").select("*").eq("tenant_id",user["id"]).execute().data}
        from api.services.access import allowed_building_ids
        units=db.table("units").select("id").in_("building_id",list(allowed_building_ids(db,user))).execute().data
        return {"leases":db.table("leases").select("*").in_("unit_id",[u["id"] for u in units]).execute().data if units else []}
    except Exception as exc: fail_closed(exc,"leases_list")


@router.post("/leases")
def create_lease(payload:dict,user:dict=Depends(require_role(["landlord"]))):
    tenant_id=payload.get("tenant_id"); unit_id=payload.get("unit_id"); start=payload.get("start_date"); end=payload.get("end_date")
    if not all((tenant_id,unit_id,start,end)): raise HTTPException(422,"Tenant, unit, start date, and end date are required.")
    if start >= end: raise HTTPException(422,"Lease end date must be after the start date.")
    db=db_for(user)
    try:
        unit_for_staff(db,user,unit_id); _owned_tenant(db,user,tenant_id)
        document_path=payload.get("document_path")
        if document_path and not str(document_path).startswith(f"leases/{user['id']}/"): raise HTTPException(422,"Lease document path is invalid.")
        db.table("leases").insert({"tenant_id":tenant_id,"unit_id":unit_id,"landlord_id":user["id"],"start_date":start,"end_date":end,"document_path":document_path,"move_in_notes":str(payload.get("move_in_notes", ""))[:4000],"status":"active"}).execute()
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"lease_create")
    return {"status":"success"}


@router.patch("/leases/{lease_id}")
def update_lease(lease_id:str,payload:dict,user:dict=Depends(require_role(["landlord"]))):
    allowed={k:payload[k] for k in ("status","end_date","move_in_notes","move_out_notes","document_path") if k in payload}
    if allowed.get("status") not in {None,"active","renewed","terminated","ended"}: raise HTTPException(422,"Invalid lease status.")
    db=db_for(user)
    try:
        rows=db.table("leases").select("unit_id").eq("id",lease_id).limit(1).execute().data
        if not rows: raise HTTPException(404,"Lease not found.")
        unit_for_staff(db,user,rows[0]["unit_id"]); db.table("leases").update(allowed).eq("id",lease_id).execute()
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"lease_update")
    return {"status":"success"}


@router.post("/privacy-requests")
def privacy_request(payload:dict,user:dict=Depends(require_role(["tenant"]))):
    kind=payload.get("request_type"); message=str(payload.get("message","")).strip()
    if kind not in {"access", "correction","deletion"}: raise HTTPException(422,"Choose access, correction, or deletion.")
    if len(message)>2000: raise HTTPException(422,"Message must not exceed 2,000 characters.")
    message = message or f"Tenant requested {kind} of their personal data."
    try: db_for(user).table("privacy_requests").insert({"tenant_id":user["id"],"request_type":kind,"message":message,"status":"open"}).execute()
    except Exception as exc: fail_closed(exc,"privacy_request")
    return {"status":"success","message":"Your request was recorded and will be handled manually."}


@router.get("/privacy-requests")
def list_privacy_requests(user:dict=Depends(get_current_user)):
    db=db_for(user)
    try:
        if user.get("role")=="tenant": return {"requests":db.table("privacy_requests").select("*").eq("tenant_id",user["id"]).execute().data}
        if user.get("role")!="landlord": raise HTTPException(403,"Access denied.")
        return {"requests":db.table("privacy_requests").select("*").eq("landlord_id",user["id"]).execute().data}
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"privacy_requests_list")
