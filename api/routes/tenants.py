from fastapi import APIRouter, HTTPException, Depends
from api.models import TenantAssignRequest
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import require_role
from api.services.ledger import generate_account_number, calculate_tenant_ledger
from api.services.email import send_welcome_email
from api.services.access import db_for, tenant_for_session, fail_closed
import uuid

router = APIRouter(prefix="/tenants", tags=["Tenants"])

STAFF = ["landlord", "caretaker"]

@router.get("/me")
def get_my_profile(user: dict = Depends(require_role(["tenant"]))):
    db = db_for(user)
    try:
        tenant = tenant_for_session(db, user)
        unit = db.table("units").select("building_id,unit_number").eq("id", tenant.get("unit_id")).limit(1).execute().data if tenant.get("unit_id") else []
        building_id = unit[0].get("building_id") if unit else None
        contact = {}
        if building_id:
            building = db.table("buildings").select("landlord_id").eq("id", building_id).limit(1).execute().data
            if building:
                landlord = db.table("landlords").select("name,email,contact").eq("id", building[0].get("landlord_id")).limit(1).execute().data
                contact = landlord[0] if landlord else {}
        safe = {k: tenant.get(k) for k in ("id", "full_name", "email", "phone_number", "emergency_contact", "emergency_phone", "unit_id", "monthly_rent", "account_number", "is_active", "is_approved", "email_verified", "lease_start_date", "lease_end_date", "deposit_amount", "deposit_returned")}
        safe["unit_number"] = unit[0].get("unit_number") if unit else None
        safe["support_contact"] = {"name": contact.get("name", "Property manager"), "email": contact.get("email", ""), "phone": contact.get("contact", "")}
        return {"tenant": safe}
    except HTTPException:
        raise
    except Exception as exc:
        fail_closed(exc, "tenant_profile")

@router.put("/me")
def update_my_profile(payload: dict, user: dict = Depends(require_role(["tenant"]))):
    allowed = {key: str(payload[key]).strip()[:160] for key in ("full_name", "phone_number", "emergency_contact", "emergency_phone") if key in payload}
    if not allowed:
        raise HTTPException(422, "Provide at least one profile field to update.")
    if not allowed.get("full_name", "x"):
        raise HTTPException(422, "Name cannot be blank.")
    try:
        db_for(user).table("tenants").update(allowed).eq("id", user["id"]).execute()
    except Exception as exc:
        fail_closed(exc, "tenant_profile_update")
    return {"status": "success", "message": "Profile updated."}


@router.get("")
def get_tenants(
    building_id: str = None,
    current_user: dict = Depends(require_role(STAFF)),
):
    db = get_supabase_client()
    try:
        tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data
        units = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
        buildings = db.buildings if hasattr(db, "buildings") else db.table("buildings").select("*").execute().data
        payments = db.payments if hasattr(db, "payments") else db.table("payments").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load tenants: {str(e)}")

    results = []
    for t in tenants:
        unit = next((u for u in units if u.get("id") == t.get("unit_id")), {})
        bldg = next((b for b in buildings if b.get("id") == unit.get("building_id")), {})

        if building_id and unit.get("building_id") != building_id:
            continue

        t_payments = [p for p in payments if p.get("tenant_id") == t.get("id")]
        ledger = calculate_tenant_ledger(t.get("monthly_rent", 0), t_payments)

        # Never return password field
        t_copy = {k: v for k, v in t.items() if k != "password"}
        t_copy["unit_number"] = unit.get("unit_number", "N/A")
        t_copy["building_name"] = bldg.get("name", "N/A")
        t_copy["ledger"] = ledger
        results.append(t_copy)

    return {"tenants": results}


@router.post("")
def assign_tenant(
    req: TenantAssignRequest,
    current_user: dict = Depends(require_role(["landlord"])),
):
    db = get_supabase_client()
    try:
        units = db.units if hasattr(db, "units") else db.table("units").select("*").execute().data
        buildings = db.buildings if hasattr(db, "buildings") else db.table("buildings").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load data: {str(e)}")

    unit = next((u for u in units if u.get("id") == req.unit_id), None)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    bldg = next((b for b in buildings if b.get("id") == unit.get("building_id")), {})
    bldg_name = bldg.get("name", "BLDG")
    account_number = generate_account_number("001", bldg_name, unit.get("unit_number", "101"))

    new_tenant = {
        "id": str(uuid.uuid4()),
        "unit_id": req.unit_id,
        "full_name": req.full_name,
        "phone_number": req.phone_number,
        "email": req.email,
        "account_number": account_number,
        "lease_start_date": req.lease_start_date or None,
        "monthly_rent": req.monthly_rent,
        "is_active": True,
        "is_approved": True,
    }

    unit["status"] = "occupied"
    if hasattr(db, "tenants"):
        db.tenants.append(new_tenant)
    else:
        try:
            db.table("tenants").insert(new_tenant).execute()
            db.table("units").update({"status": "occupied"}).eq("id", req.unit_id).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to assign tenant: {str(e)}")

    return {"status": "success", "tenant": {k: v for k, v in new_tenant.items() if k != "password"}}


@router.post("/{tenant_id}/send-welcome")
def trigger_welcome_email(
    tenant_id: str,
    current_user: dict = Depends(require_role(["landlord"])),
):
    db = get_supabase_client()
    try:
        tenants = db.tenants if hasattr(db, "tenants") else db.table("tenants").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load tenants: {str(e)}")

    tenant = next((t for t in tenants if t.get("id") == tenant_id), None)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    send_welcome_email(
        tenant_email=tenant.get("email"),
        tenant_name=tenant.get("full_name"),
        account_number=tenant.get("account_number"),
        paybill="247247",
        due_date="5th of every month"
    )
    return {"status": "success", "message": f"Welcome email dispatched to {tenant.get('full_name')}"}


@router.delete("/all")
def delete_all_tenants(
    current_user: dict = Depends(require_role(["landlord"])),
):
    """Hard-delete ALL tenants from the database."""
    db = get_supabase_client()
    if hasattr(db, "tenants"):
        count = len(db.tenants)
        db.tenants.clear()
        return {"status": "success", "message": f"Removed all {count} tenants."}
    else:
        try:
            # Fetch all tenant IDs first
            res = db.table("tenants").select("id").execute()
            if not res.data:
                return {"status": "success", "message": "No tenants to remove."}
            count = len(res.data)
            # Hard delete all rows
            db.table("tenants").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            return {"status": "success", "message": f"Removed all {count} tenants."}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to remove tenants: {str(e)}")


@router.delete("/{tenant_id}")
def delete_tenant(
    tenant_id: str,
    current_user: dict = Depends(require_role(["landlord"])),
):
    db = get_supabase_client()
    if hasattr(db, "tenants"):
        tenant = next((t for t in db.tenants if t.get("id") == tenant_id), None)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        if hasattr(db, "units"):
            unit = next((u for u in db.units if u.get("id") == tenant.get("unit_id")), None)
            if unit:
                unit["status"] = "vacant"
        db.tenants.remove(tenant)
        return {"status": "success", "message": f"Tenant {tenant.get('full_name')} removed successfully"}
    else:
        try:
            # Hard delete from database
            res = db.table("tenants").delete().eq("id", tenant_id).execute()
            if not res.data:
                raise HTTPException(status_code=404, detail="Tenant not found")
            tenant_unit = res.data[0].get("unit_id") if res.data else None
            if tenant_unit:
                db.table("units").update({"status": "vacant"}).eq("id", tenant_unit).execute()
            return {"status": "success", "message": "Tenant removed successfully"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to remove tenant: {str(e)}")
