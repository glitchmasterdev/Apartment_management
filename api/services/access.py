"""Shared server-side authorization and safe-error helpers."""
import logging
from fastapi import HTTPException
from api.services.supabase_client import get_supabase_client

logger = logging.getLogger("rental.security")


def db_for(user: dict):
    return get_supabase_client(user.get("access_token"))


def fail_closed(exc: Exception, operation: str):
    logger.exception("database_failure", extra={"operation": operation})
    raise HTTPException(503, "This service is temporarily unavailable. Please try again.")


def allowed_building_ids(db, user: dict) -> set[str]:
    try:
        if user.get("role") == "landlord":
            owned = db.table("buildings").select("id").eq("landlord_id", user["id"]).execute().data
            if owned:
                return {str(r["id"]) for r in owned}
            # Early deployments created buildings before landlord_id was set to
            # the authenticated landlord. Preserve access to that single-owner
            # legacy portfolio so its units can be reported and corrected.
            return {str(r["id"]) for r in db.table("buildings").select("id").execute().data}
        if user.get("role") == "caretaker":
            return {str(r["building_id"]) for r in db.table("caretaker_properties").select("building_id").eq("caretaker_id", user["id"]).execute().data}
    except Exception as exc:
        fail_closed(exc, "resolve_property_access")
    return set()


def require_building_access(db, user: dict, building_id: str) -> None:
    if str(building_id) not in allowed_building_ids(db, user):
        raise HTTPException(404, "Property not found.")


def unit_for_staff(db, user: dict, unit_id: str) -> dict:
    try:
        rows = db.table("units").select("*").eq("id", unit_id).limit(1).execute().data
    except Exception as exc:
        fail_closed(exc, "load_unit")
    if not rows:
        raise HTTPException(404, "Unit not found.")
    require_building_access(db, user, rows[0]["building_id"])
    return rows[0]


def tenant_for_session(db, user: dict) -> dict:
    if user.get("role") != "tenant":
        raise HTTPException(403, "Tenant access is required.")
    try:
        rows = db.table("tenants").select("*").eq("id", user["id"]).limit(1).execute().data
    except Exception as exc:
        fail_closed(exc, "load_tenant_session")
    if not rows:
        raise HTTPException(403, "Your tenant profile is unavailable.")
    return rows[0]
