from fastapi import APIRouter, HTTPException, Depends
from api.models import BuildingCreate, UnitCreate, BulkUnitsImport, UnitUpdate, BuildingUpdate
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import get_current_user, require_role
from api.services.access import allowed_building_ids, require_building_access
import uuid
import secrets
from datetime import datetime, timezone

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


def _ensure_landlord_profile(db, current_user: dict) -> str:
    """Return the landlord profile ID, provisioning the legacy account once.

    Landlord logins predate the Supabase ``profiles`` table in some deployed
    databases. Buildings reference ``profiles.id``, so a placeholder ID from
    the legacy login row cannot be inserted. The service-role client can make
    the one-time Auth/profile bridge without exposing credentials to a browser.
    """
    existing_profile_id = _get_landlord_id(db)
    if existing_profile_id:
        return existing_profile_id

    email = str(current_user.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=409, detail="Your landlord account has no email address to configure its profile.")

    try:
        users_response = db.auth.admin.list_users()
        users = getattr(users_response, "users", None) or getattr(users_response, "data", None) or []
        auth_user = next((user for user in users if str(getattr(user, "email", "")).lower() == email), None)
        if not auth_user:
            created = db.auth.admin.create_user({
                "email": email,
                "email_confirm": True,
                # The custom landlord login remains authoritative. This is a
                # non-disclosed bridge credential required only by the FK.
                "password": secrets.token_urlsafe(32),
            })
            auth_user = getattr(created, "user", None) or getattr(created, "data", None)
        auth_user_id = (
            str(auth_user.get("id", ""))
            if isinstance(auth_user, dict)
            else str(getattr(auth_user, "id", ""))
        )
        if not auth_user_id:
            raise RuntimeError("Supabase did not return an authentication user ID.")

        db.table("profiles").insert({
            "id": auth_user_id,
            "full_name": str(current_user.get("full_name") or "Landlord")[:200],
            "role": "landlord",
        }).execute()
        return auth_user_id
    except HTTPException:
        raise
    except Exception as exc:
        # A concurrent first property request can create the profile between
        # our initial read and insert. Reuse it instead of reporting failure.
        profile_id = _get_landlord_id(db)
        if profile_id:
            return profile_id
        raise HTTPException(status_code=503, detail="Unable to configure the landlord profile. Please try again.") from exc


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
    if req.total_floors is not None and req.total_floors < 1:
        raise HTTPException(status_code=422, detail="Total floors must be at least 1.")
    new_bldg = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "location": req.location or "",
        "total_floors": req.total_floors or 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if hasattr(db, "buildings"):
        db.buildings.append(new_bldg)
        return {"status": "success", "building": new_bldg}
    landlord_profile_id = _ensure_landlord_profile(db, current_user)
    new_bldg["landlord_id"] = landlord_profile_id
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
        buildings_list = db.buildings if hasattr(db, "buildings") else db.table("buildings").select("id,name").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load units: {str(e)}")
    allowed_ids = allowed_building_ids(db, current_user)
    if building_id:
        require_building_access(db, current_user, building_id)
        units_list = [u for u in units_list if str(u.get("building_id")) == str(building_id)]
    else:
        units_list = [u for u in units_list if str(u.get("building_id")) in allowed_ids]
    building_names = {str(building.get("id")): building.get("name") for building in buildings_list}
    for u in units_list:
        tenant = next((t for t in tenants_list if t.get("unit_id") == u.get("id") and t.get("is_active")), None)
        u["tenant"] = {k: v for k, v in tenant.items() if k != "password"} if tenant else None
        u["building_name"] = building_names.get(str(u.get("building_id")), "Unknown building")
    return {"units": units_list}


@router.get("/units/public")
def get_available_units(building_id: str = None):
    """Public/tenant listing: expose only rentable vacant units, never tenant data."""
    db = get_supabase_client()
    try:
        units = db.units if hasattr(db, "units") else db.table("units").select("id,unit_number,floor,rent_amount,status,building_id,is_active").eq("status", "vacant").execute().data
        if building_id and _safe_uuid(building_id):
            units = [u for u in units if str(u.get("building_id")) == str(building_id)]
        available = [u for u in units if u.get("status") == "vacant" and u.get("is_active", True)]
        return {"units": [{key: unit.get(key) for key in ("id", "unit_number", "floor", "rent_amount", "status", "building_id")} for unit in available]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Available units are temporarily unavailable.")


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
    skipped_units = []
    existing = set()
    if not hasattr(db, "units"):
        existing = {str(u["unit_number"]).strip().lower() for u in db.table("units").select("unit_number").eq("building_id", building_id).execute().data}
    for row in req.csv_data:
        unit_no = str(row.get("Unit Number", row.get("unit_number", ""))).strip()[:20]
        if not unit_no:
            continue
        key = unit_no.lower()
        if key in existing:
            skipped_units.append(unit_no)
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
            if any(str(u.get("unit_number", "")).strip().lower() == key and u.get("building_id") == building_id for u in db.units):
                skipped_units.append(unit_no)
                continue
            db.units.append(new_unit)
        else:
            try:
                db.table("units").insert(new_unit).execute()
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to import unit '{unit_no}': {str(e)}")
        created_count += 1
        existing.add(key)
    return {"status": "success", "imported_count": created_count, "skipped_count": len(skipped_units), "skipped_units": skipped_units}


@router.delete("/buildings/{building_id}")
def delete_building(building_id: str, current_user: dict = Depends(require_role(["landlord"]))):
    """Remove a property only after every unit has been vacated."""
    db = get_supabase_client()
    if hasattr(db, "buildings"):
        units = [unit for unit in db.units if str(unit.get("building_id")) == str(building_id)]
        if any(unit.get("status") == "occupied" for unit in units):
            raise HTTPException(status_code=409, detail="This building still has occupied units. Move out or delete the tenant records before deleting the building.")
        db.buildings[:] = [b for b in db.buildings if b.get("id") != building_id]
        db.units[:] = [u for u in db.units if u.get("building_id") != building_id]
        return {"status": "success"}
    try:
        # Verify the property exists and belongs to the landlord's accessible
        # portfolio before removing any related records.
        require_building_access(db, current_user, building_id)
        units = db.table("units").select("id,status").eq("building_id", building_id).execute().data
        if any(unit.get("status") == "occupied" for unit in units):
            raise HTTPException(status_code=409, detail="This building still has occupied units. Move out or delete the tenant records before deleting the building.")
        unit_ids = [u["id"] for u in units]
        if unit_ids:
            tenant_rows = db.table("tenants").select("id").in_("unit_id", unit_ids).execute().data
            tenant_ids = [tenant["id"] for tenant in tenant_rows]

            # Delete child rows first. In particular, leases.unit_id does not
            # cascade in existing installations, which previously prevented a
            # building with tenancy history from being deleted.
            for table in ("maintenance_requests", "occupancy_logs", "payments", "leases"):
                try: db.table(table).delete().in_("unit_id", unit_ids).execute()
                except Exception: pass
            if tenant_ids:
                for table in ("privacy_requests",):
                    try: db.table(table).delete().in_("tenant_id", tenant_ids).execute()
                    except Exception: pass
                db.table("tenants").delete().in_("id", tenant_ids).execute()
            db.table("units").delete().eq("building_id", building_id).execute()
        db.table("expenses").delete().eq("building_id", building_id).execute()
        try: db.table("caretaker_properties").delete().eq("building_id", building_id).execute()
        except Exception: pass
        db.table("buildings").delete().eq("id", building_id).execute()
        return {"status": "success"}
    except HTTPException: raise
    except Exception as exc:
        raise HTTPException(400, detail=f"Could not delete property: {exc}")


@router.delete("/units/{unit_id}")
def delete_unit(unit_id: str, current_user: dict = Depends(require_role(["landlord"]))):
    """Delete a vacant unit; occupied units must be moved out first."""
    db = get_supabase_client()
    try:
        if hasattr(db, "units"):
            unit = next((row for row in db.units if str(row.get("id")) == str(unit_id)), None)
            if not unit:
                raise HTTPException(status_code=404, detail="Unit not found.")
            if unit.get("status") == "occupied":
                raise HTTPException(status_code=409, detail="Move out the tenant before deleting this occupied unit.")
            db.units.remove(unit)
            return {"status": "success", "message": "Vacant unit deleted."}

        unit_rows = db.table("units").select("id,building_id,status").eq("id", unit_id).limit(1).execute().data
        if not unit_rows:
            raise HTTPException(status_code=404, detail="Unit not found.")
        unit = unit_rows[0]
        require_building_access(db, current_user, unit["building_id"])
        if unit.get("status") == "occupied":
            raise HTTPException(status_code=409, detail="Move out the tenant before deleting this occupied unit.")
        db.table("units").delete().eq("id", unit_id).execute()
        return {"status": "success", "message": "Vacant unit deleted."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, detail=f"Could not delete unit: {exc}")


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
