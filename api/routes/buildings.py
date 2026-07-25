from fastapi import APIRouter, HTTPException
from api.models import BuildingCreate, UnitCreate, BulkUnitsImport, UnitUpdate, BuildingUpdate
from api.services.supabase_client import get_supabase_client
import uuid

router = APIRouter(prefix="", tags=["Buildings & Units"])

@router.get("/buildings")
def get_buildings():
    db = get_supabase_client()
    if hasattr(db, "buildings"):
        return {"buildings": db.buildings}
    res = db.table("buildings").select("*").execute()
    return {"buildings": res.data}

@router.post("/buildings")
def create_building(req: BuildingCreate):
    db = get_supabase_client()
    new_bldg = {
        "id": str(uuid.uuid4()),
        "landlord_id": "landlord-1",
        "name": req.name,
        "location": req.location,
        "total_floors": req.total_floors,
        "created_at": "2026-07-24T12:00:00Z"
    }
    if hasattr(db, "buildings"):
        db.buildings.append(new_bldg)
    else:
        db.table("buildings").insert(new_bldg).execute()
    return {"status": "success", "building": new_bldg}

@router.put("/buildings/{building_id}")
def update_building(building_id: str, req: BuildingUpdate):
    db = get_supabase_client()
    if hasattr(db, "buildings"):
        bldg = next((b for b in db.buildings if b.get("id") == building_id), None)
        if not bldg:
            raise HTTPException(status_code=404, detail="Building not found")
        if req.name is not None:
            bldg["name"] = req.name
        if req.location is not None:
            bldg["location"] = req.location
        return {"status": "success", "building": bldg}
    else:
        update_data = {}
        if req.name is not None:
            update_data["name"] = req.name
        if req.location is not None:
            update_data["location"] = req.location
        res = db.table("buildings").update(update_data).eq("id", building_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Building not found")
        return {"status": "success", "building": res.data[0]}

@router.get("/units")
def get_units(building_id: str = None):
    db = get_supabase_client()
    units_list = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
    tenants_list = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data

    if building_id:
        units_list = [u for u in units_list if u.get("building_id") == building_id]

    # Attach tenant detail if occupied
    for u in units_list:
        tenant = next((t for t in tenants_list if t.get("unit_id") == u.get("id") and t.get("is_active")), None)
        u["tenant"] = tenant

    return {"units": units_list}

@router.post("/units")
def create_unit(req: UnitCreate):
    db = get_supabase_client()
    new_unit = {
        "id": str(uuid.uuid4()),
        "building_id": req.building_id,
        "unit_number": req.unit_number,
        "floor": req.floor,
        "rent_amount": req.rent_amount,
        "deposit_amount": req.deposit_amount or req.rent_amount,
        "deposit_paid": False,
        "status": "vacant",
        "is_active": True
    }
    if hasattr(db, "units"):
        db.units.append(new_unit)
    else:
        db.table("units").insert(new_unit).execute()
    return {"status": "success", "unit": new_unit}

@router.put("/units/{unit_id}")
def update_unit(unit_id: str, req: UnitUpdate):
    db = get_supabase_client()
    if hasattr(db, "units"):
        unit = next((u for u in db.units if u.get("id") == unit_id), None)
        if not unit:
            raise HTTPException(status_code=404, detail="Unit not found")
        if req.unit_number is not None:
            unit["unit_number"] = req.unit_number
        if req.floor is not None:
            unit["floor"] = req.floor
        if req.rent_amount is not None:
            unit["rent_amount"] = req.rent_amount
        if req.status is not None:
            unit["status"] = req.status
        if req.building_id is not None:
            unit["building_id"] = req.building_id
        return {"status": "success", "unit": unit}
    else:
        update_data = {}
        if req.unit_number is not None:
            update_data["unit_number"] = req.unit_number
        if req.floor is not None:
            update_data["floor"] = req.floor
        if req.rent_amount is not None:
            update_data["rent_amount"] = req.rent_amount
        if req.status is not None:
            update_data["status"] = req.status
        if req.building_id is not None:
            update_data["building_id"] = req.building_id
        res = db.table("units").update(update_data).eq("id", unit_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Unit not found")
        return {"status": "success", "unit": res.data[0]}

@router.post("/units/bulk-import")
def bulk_import_units(req: BulkUnitsImport):
    db = get_supabase_client()
    created_count = 0
    for row in req.csv_data:
        unit_no = str(row.get("Unit Number", row.get("unit_number", ""))).strip()
        if not unit_no:
            continue
        new_unit = {
            "id": f"u-{uuid.uuid4().hex[:6]}",
            "building_id": req.building_id,
            "unit_number": unit_no,
            "floor": int(row.get("Floor", row.get("floor", 1))),
            "rent_amount": float(row.get("Rent", row.get("rent_amount", 30000))),
            "deposit_amount": float(row.get("Deposit", row.get("deposit_amount", 30000))),
            "deposit_paid": False,
            "status": "vacant",
            "is_active": True
        }
        if hasattr(db, "units"):
            db.units.append(new_unit)
        else:
            db.table("units").insert(new_unit).execute()
        created_count += 1
    return {"status": "success", "imported_count": created_count}

@router.get("/settings")
def get_settings():
    db = get_supabase_client()
    if hasattr(db, "system_settings"):
        return {s["key"]: s["value"] for s in db.system_settings}
    else:
        res = db.table("system_settings").select("*").execute()
        return {s["key"]: s["value"] for s in res.data}

@router.put("/settings")
def update_settings(req: dict):
    db = get_supabase_client()
    if hasattr(db, "system_settings"):
        for k, v in req.items():
            setting = next((s for s in db.system_settings if s["key"] == k), None)
            if setting:
                setting["value"] = str(v)
            else:
                db.system_settings.append({"key": k, "value": str(v)})
        return {"status": "success", "settings": {s["key"]: s["value"] for s in db.system_settings}}
    else:
        for k, v in req.items():
            db.table("system_settings").upsert({"key": k, "value": str(v)}).execute()
        res = db.table("system_settings").select("*").execute()
        return {"status": "success", "settings": {s["key"]: s["value"] for s in res.data}}
