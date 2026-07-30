from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from api.services.auth_middleware import require_role
from api.services.access import db_for, allowed_building_ids, require_building_access, fail_closed

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])

@router.get("/dashboard")
def dashboard(building_id: str | None = None, current_user: dict = Depends(require_role(["landlord"]))):
    db=db_for(current_user)
    try:
        ids=[building_id] if building_id else list(allowed_building_ids(db,current_user))
        if building_id: require_building_access(db,current_user,building_id)
        units=db.table("units").select("id,status,rent_amount,building_id").in_("building_id",ids).execute().data if ids else []
        unit_ids=[u["id"] for u in units]
        payments=db.table("payments").select("amount_paid,status,payment_date,unit_id").in_("unit_id",unit_ids).eq("status","approved").execute().data if unit_ids else []
        current_month=date.today().strftime("%Y-%m")
        revenue=sum(float(p.get("amount_paid") or 0) for p in payments if str(p.get("payment_date","")).startswith(current_month))
        total=len(units); occupied=sum(u.get("status")=="occupied" for u in units)
        return {"kpis":{"total_units":total,"occupied_units":occupied,"occupancy_rate":round(100*occupied/total,1) if total else 0,"monthly_revenue":revenue},"report_period":current_month}
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"dashboard_report")

@router.get("/occupancy")
def occupancy(building_id: str | None = None, current_user: dict = Depends(require_role(["landlord"]))):
    return dashboard(building_id,current_user)["kpis"]
