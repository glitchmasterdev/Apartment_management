from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from api.models import OccupancyMoveIn, OccupancyMoveOut, BulkDailyPresence
from api.services.auth_middleware import require_role
from api.services.access import db_for, require_building_access, unit_for_staff, fail_closed

router = APIRouter(prefix="/occupancy", tags=["Occupancy & Caretaker"])
STAFF = ["landlord", "caretaker"]


def _tenant_in_unit(db, tenant_id, unit_id):
    rows = db.table("tenants").select("id").eq("id", tenant_id).eq("unit_id", unit_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Tenant assignment not found.")


def _record(db, unit_id, tenant_id, action, user, notes):
    db.table("occupancy_logs").insert({"unit_id": unit_id, "tenant_id": tenant_id, "action_type": action,
        "performed_by": user["id"], "notes": notes, "timestamp": datetime.now(timezone.utc).isoformat()}).execute()


@router.post("/sign-in")
def move_in_tenant(req: OccupancyMoveIn, current_user: dict = Depends(require_role(STAFF))):
    db = db_for(current_user)
    try:
        unit_for_staff(db, current_user, req.unit_id)
        _tenant_in_unit(db, req.tenant_id, req.unit_id)
        db.table("units").update({"status": "occupied"}).eq("id", req.unit_id).execute()
        _record(db, req.unit_id, req.tenant_id, "MOVE_IN", current_user, req.notes or "Move-in completed")
    except HTTPException: raise
    except Exception as exc: fail_closed(exc, "move_in")
    return {"status": "success", "message": "Tenant move-in recorded."}


@router.post("/sign-out")
def move_out_tenant(req: OccupancyMoveOut, current_user: dict = Depends(require_role(STAFF))):
    db = db_for(current_user)
    try:
        unit_for_staff(db, current_user, req.unit_id)
        _tenant_in_unit(db, req.tenant_id, req.unit_id)
        db.table("tenants").update({"is_active": False}).eq("id", req.tenant_id).execute()
        db.table("units").update({"status": "vacant"}).eq("id", req.unit_id).execute()
        _record(db, req.unit_id, req.tenant_id, "MOVE_OUT", current_user, req.notes)
    except HTTPException: raise
    except Exception as exc: fail_closed(exc, "move_out")
    return {"status": "success", "message": "Tenant move-out recorded."}


@router.post("/daily-presence/bulk")
def bulk_daily_presence(req: BulkDailyPresence, current_user: dict = Depends(require_role(STAFF))):
    if req.action.lower() not in {"present", "absent"}:
        raise HTTPException(422, "Action must be 'present' or 'absent'.")
    db = db_for(current_user)
    try:
        require_building_access(db, current_user, req.building_id)
        units = db.table("units").select("id").eq("building_id", req.building_id).eq("status", "occupied").execute().data
        action = "DAILY_PRESENT" if req.action.lower() == "present" else "DAILY_ABSENT"
        for unit in units: _record(db, unit["id"], None, action, current_user, "Bulk caretaker scan")
    except HTTPException: raise
    except Exception as exc: fail_closed(exc, "bulk_presence")
    return {"status": "success", "message": f"Recorded {req.action.lower()} for {len(units)} occupied units."}
