from fastapi import APIRouter, HTTPException
from api.models import OccupancyMoveIn, OccupancyMoveOut, BulkDailyPresence
from api.services.supabase_client import get_supabase_client
import uuid
from datetime import datetime

router = APIRouter(prefix="/occupancy", tags=["Occupancy & Caretaker"])

@router.post("/sign-in")
def move_in_tenant(req: OccupancyMoveIn):
    db = get_supabase_client()
    units = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
    unit = next((u for u in units if u.get("id") == req.unit_id), None)
    if unit:
        unit["status"] = "occupied"

    log_entry = {
        "id": f"occ-{uuid.uuid4().hex[:6]}",
        "unit_id": req.unit_id,
        "tenant_id": req.tenant_id,
        "action_type": "MOVE_IN",
        "timestamp": datetime.now().isoformat(),
        "performed_by": "caretaker-1",
        "notes": req.notes or "Move in completed"
    }
    if hasattr(db, "occupancy_logs"):
        db.occupancy_logs.append(log_entry)

    return {"status": "success", "message": "Tenant move-in recorded", "log": log_entry}

@router.post("/sign-out")
def move_out_tenant(req: OccupancyMoveOut):
    db = get_supabase_client()
    units = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
    tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data

    unit = next((u for u in units if u.get("id") == req.unit_id), None)
    tenant = next((t for t in tenants if t.get("id") == req.tenant_id), None)

    if unit:
        unit["status"] = "vacant"
    if tenant:
        tenant["is_active"] = False

    log_entry = {
        "id": f"occ-{uuid.uuid4().hex[:6]}",
        "unit_id": req.unit_id,
        "tenant_id": req.tenant_id,
        "action_type": "MOVE_OUT",
        "timestamp": datetime.now().isoformat(),
        "performed_by": "caretaker-1",
        "notes": req.notes  # Mandatory move-out notes (damages/withholdings)
    }
    if hasattr(db, "occupancy_logs"):
        db.occupancy_logs.append(log_entry)

    return {
        "status": "success",
        "message": "Tenant move-out recorded. Deposit reconciliation pending review of notes.",
        "log": log_entry
    }

@router.post("/daily-presence/bulk")
def bulk_daily_presence(req: BulkDailyPresence):
    db = get_supabase_client()
    units = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data

    bldg_units = [u for u in units if u.get("building_id") == req.building_id and u.get("status") == "occupied"]
    action_type = "DAILY_PRESENT" if req.action.lower() == "present" else "DAILY_ABSENT"
    logged_count = 0

    for u in bldg_units:
        log_entry = {
            "id": f"occ-{uuid.uuid4().hex[:6]}",
            "unit_id": u.get("id"),
            "tenant_id": None,
            "action_type": action_type,
            "timestamp": datetime.now().isoformat(),
            "performed_by": "caretaker-1",
            "notes": f"Bulk caretaker scan: {req.action.upper()}"
        }
        if hasattr(db, "occupancy_logs"):
            db.occupancy_logs.append(log_entry)
        logged_count += 1

    return {"status": "success", "message": f"Recorded {req.action.upper()} for {logged_count} units"}
