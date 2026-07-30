from fastapi import APIRouter, HTTPException, Depends
from api.models import BuildingCreate, UnitCreate, BulkUnitsImport, UnitUpdate, BuildingUpdate
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import get_current_user, require_role
import uuid
from datetime import datetime

router = APIRouter(prefix="", tags=["Buildings & Units"])

STAFF = ["landlord", "caretaker"]

def _safe_uuid(val):
    if not val:
        return None
    try:
        import uuid as _u; _u.UUID(str(val)); return str(val)
    except (ValueError, AttributeError):
        return None

def _get_landlord_id(db):
    try:
        res = db.table("profiles").select("id").eq("role", "landlord").limit(1).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass
    return None


@router.get("/buildings")
def get_buildings(current_user: dict = Depends(require_role(STAFF))):
    db = get_supabase_client()
    if hasattr(db, "buildings"):
        return {"buildings": db.buildings}
    try:
        res = db.table("buildings").select("*").execute()
        return {"buildings": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load buildings: {str(e)}")


@router.post("/buildings")
def create_building(req: BuildingCreate, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    new_bldg = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "location": req.location or "",
        "total_floors": req.total_floors or 0,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    if hasattr(db, "buildings"):
        db.buildings.append(new_bldg)
        return {"status": "success", "building": new_bldg}
    landlord_id = _get_landlord_id(db)
    if landlord_id:
        new_bldg["landlord_id"] = landlord_id
    try:
        db.table("buildings").insert(new_bldg).execute()
        return {"status": "success", "building": new_bldg}
    except Exception as e:
        err = str(e)
        if "landlord_id" in err and "not-null" in err.lower():
            raise HTTPException(status_code=400, detail="Run: ALTER TABLE buildings ALTER COLUMN landlord_id DROP NOT NULL; in your Supabase SQL editor.")
        raise HTTPException(status_code=400, detail=f"Failed to create property: {err}")


@router.put("/buildings/{building_id}")
def update_building(building_id: str, req: BuildingUpdate, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    if hasattr(db, "buildings"):
        bldg = next((b for b in db.buildings if b.get("id") == building_id), None)
        if not bldg:
            raise HTTPException(status_code=404, detail="Building not found")
        if req.name is not None: bldg["name"] = req.name
        if req.location is not None: bldg["location"] = req.location
        return {"status": "success", "building": bldg}
    try:
        update_data = {}
        if req.name is not None: update_data["name"] = req.name
        if req.location is not None: update_data["location"] = req.location
        res = db.table("buildings").update(update_data).eq("id", building_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Building not found")
        return {"status": "success", "building": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update building: {str(e)}")


@router.get("/units")
def get_units(building_id: str = None, current_user: dict = Depends(require_role(STAFF))):
    db = get_supabase_client()
    try:
        units_list = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
        tenants_list = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load units: {str(e)}")
    if building_id and _safe_uuid(building_id):
        units_list = [u for u in units_list if u.get("building_id") == building_id]
    for u in units_list:
        tenant = next((t for t in tenants_list if t.get("unit_id") == u.get("id") and t.get("is_active")), None)
        u["tenant"] = {k: v for k, v in tenant.items() if k != "password"} if tenant else None
    return {"units": units_list}


@router.post("/units")
def create_unit(req: UnitCreate, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    building_id = _safe_uuid(req.building_id)
    if not building_id and not hasattr(db, "units"):
        raise HTTPException(status_code=400, detail="Please select a valid property before adding a unit.")
    new_unit = {
        "id": str(uuid.uuid4()),
        "unit_number": req.unit_number,
        "floor": req.floor or 1,
        "rent_amount": req.rent_amount,
        "deposit_amount": req.deposit_amount or req.rent_amount,
        "deposit_paid": False,
        "status": "vacant",
        "is_active": True,
    }
    if building_id:
        new_unit["building_id"] = building_id
    if hasattr(db, "units"):
        db.units.append(new_unit)
        return {"status": "success", "unit": new_unit}
    try:
        db.table("units").insert(new_unit).execute()
        return {"status": "success", "unit": new_unit}
    except Exception as e:
        err = str(e)
        if "building_id" in err:
            raise HTTPException(status_code=400, detail="Invalid or missing building. Please select a property from the dropdown.")
        raise HTTPException(status_code=400, detail=f"Failed to add unit: {err}")


@router.put("/units/{unit_id}")
def update_unit(unit_id: str, req: UnitUpdate, current_user: dict = Depends(require_role(STAFF))):
    db = get_supabase_client()
    if hasattr(db, "units"):
        unit = next((u for u in db.units if u.get("id") == unit_id), None)
        if not unit:
            raise HTTPException(status_code=404, detail="Unit not found")
        if req.unit_number is not None: unit["unit_number"] = req.unit_number
        if req.floor is not None: unit["floor"] = req.floor
        if req.rent_amount is not None: unit["rent_amount"] = req.rent_amount
        if req.status is not None: unit["status"] = req.status
        if req.building_id is not None: unit["building_id"] = req.building_id
        return {"status": "success", "unit": unit}
    try:
        update_data = {}
        if req.unit_number is not None: update_data["unit_number"] = req.unit_number
        if req.floor is not None: update_data["floor"] = req.floor
        if req.rent_amount is not None: update_data["rent_amount"] = req.rent_amount
        if req.status is not None: update_data["status"] = req.status
        if req.building_id is not None: update_data["building_id"] = req.building_id
        res = db.table("units").update(update_data).eq("id", unit_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Unit not found")
        return {"status": "success", "unit": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update unit: {str(e)}")


@router.post("/units/bulk-import")
def bulk_import_units(req: BulkUnitsImport, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    building_id = _safe_uuid(req.building_id)
    if not building_id and not hasattr(db, "units"):
        raise HTTPException(status_code=400, detail="Please select a valid property before bulk importing units.")
    if len(req.csv_data) > 500:
        raise HTTPException(status_code=400, detail="CSV import is limited to 500 rows at a time.")
    created_count = 0
    for row in req.csv_data:
        unit_no = str(row.get("Unit Number", row.get("unit_number", ""))).strip()[:20]
        if not unit_no:
            continue
        new_unit = {
            "id": str(uuid.uuid4()),
            "unit_number": unit_no,
            "floor": int(row.get("Floor", row.get("floor", 1))),
            "rent_amount": float(row.get("Rent", row.get("rent_amount", 30000))),
            "deposit_amount": float(row.get("Deposit", row.get("deposit_amount", 30000))),
            "deposit_paid": False,
            "status": "vacant",
            "is_active": True,
        }
        if building_id:
            new_unit["building_id"] = building_id
        if hasattr(db, "units"):
            db.units.append(new_unit)
        else:
            try:
                db.table("units").insert(new_unit).execute()
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to import unit '{unit_no}': {str(e)}")
        created_count += 1
    return {"status": "success", "imported_count": created_count}


@router.get("/settings")
def get_settings(current_user: dict = Depends(get_current_user)):
    db = get_supabase_client()
    if hasattr(db, "system_settings"):
        return {s["key"]: s["value"] for s in db.system_settings}
    try:
        res = db.table("system_settings").select("*").execute()
        return {s["key"]: s["value"] for s in res.data}
    except Exception:
        return {}


@router.put("/settings")
def update_settings(req: dict, current_user: dict = Depends(require_role(["landlord"]))):
    import html
    # Sanitize: strip HTML tags, enforce max length
    safe_req = {}
    for k, v in req.items():
        key = str(k)[:50]
        val = html.escape(str(v))[:500]
        safe_req[key] = val
    db = get_supabase_client()
    if hasattr(db, "system_settings"):
        for k, v in safe_req.items():
            setting = next((s for s in db.system_settings if s["key"] == k), None)
            if setting:
                setting["value"] = v
            else:
                db.system_settings.append({"key": k, "value": v})
        return {"status": "success", "settings": {s["key"]: s["value"] for s in db.system_settings}}
    try:
        for k, v in safe_req.items():
            db.table("system_settings").upsert({"key": k, "value": v}).execute()
        res = db.table("system_settings").select("*").execute()
        return {"status": "success", "settings": {s["key"]: s["value"] for s in res.data}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to save settings: {str(e)}")
