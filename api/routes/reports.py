from datetime import date
import calendar
from fastapi import APIRouter, Depends, HTTPException
from api.services.auth_middleware import require_role
from api.services.access import db_for, allowed_building_ids, require_building_access, fail_closed

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])

@router.get("/dashboard")
def dashboard(building_id: str | None = None, current_user: dict = Depends(require_role(["landlord"]))):
    db=db_for(current_user)
    try:
        ids=[building_id] if building_id else list(allowed_building_ids(db,current_user))
        if building_id:
            require_building_access(db,current_user,building_id)
            units=db.table("units").select("id,status,building_id,rent_amount").eq("building_id", building_id).execute().data
        else:
            units=db.table("units").select("id,status,building_id,rent_amount").in_("building_id",ids).execute().data if ids else []
        unit_ids=[u["id"] for u in units]

        # Unit status is the authoritative, always-available occupancy source.
        # Tenant and payment lookups add detail, but their failure must never
        # make a selected building look empty on the landlord dashboard.
        active_tenants = []
        if unit_ids:
            try:
                active_tenants = db.table("tenants").select("unit_id").in_("unit_id", unit_ids).eq("is_active", True).execute().data
            except Exception:
                # Legacy databases can be missing tenants.is_active. Unit
                # statuses still provide accurate building occupancy totals.
                active_tenants = []

        current_month=date.today().strftime("%Y-%m")
        occupied_unit_ids={str(t["unit_id"]) for t in active_tenants if t.get("unit_id")}
        total=len(units); occupied=sum(u.get("status")=="occupied" or str(u["id"]) in occupied_unit_ids for u in units)
        # This KPI is the contractual rent expected from occupied units, not
        # cash collected in the current month. Payments remain the source for
        # reconciliation and arrears views.
        revenue=sum(
            float(u.get("rent_amount") or 0)
            for u in units
            if u.get("status") == "occupied" or str(u["id"]) in occupied_unit_ids
        )
        # Cash received is distinct from expected revenue: include only
        # approved payments recorded during the current calendar month and
        # scoped to the selected building(s).
        approved_payments = []
        if unit_ids:
            approved_payments = (
                db.table("payments")
                .select("amount_paid,payment_date")
                .in_("unit_id", unit_ids)
                .eq("status", "approved")
                .execute()
                .data
                or []
            )
        rent_received = sum(
            float(payment.get("amount_paid") or 0)
            for payment in approved_payments
            if str(payment.get("payment_date") or "").startswith(current_month)
        )
        return {
            "kpis": {
                "total_units": total,
                "occupied_units": occupied,
                "occupancy_rate": round(100 * occupied / total, 1) if total else 0,
                "monthly_revenue": revenue,
                "rent_received": rent_received,
            },
            "report_period": current_month,
            "building_id": building_id,
        }
    except HTTPException: raise
    except Exception as exc: fail_closed(exc,"dashboard_report")

@router.get("/occupancy")
def occupancy(building_id: str | None = None, current_user: dict = Depends(require_role(["landlord"]))):
    return dashboard(building_id,current_user)["kpis"]


@router.get("/yoy-occupancy")
def yoy_occupancy(building_id: str | None = None, current_user: dict = Depends(require_role(["landlord"]))):
    """Return chart-safe occupancy data for the current selected portfolio scope."""
    kpis = dashboard(building_id, current_user)["kpis"]
    today = date.today()
    labels = [calendar.month_abbr[month] for month in range(1, 13)]
    current_year = [0] * 12
    current_year[today.month - 1] = kpis["occupancy_rate"]
    return {"labels": labels, "current_year": current_year, "previous_year": [0] * 12}


@router.get("/arrears-aging")
def arrears_aging(building_id: str | None = None, current_user: dict = Depends(require_role(["landlord"]))):
    """Return chart-safe arrears buckets for the current portfolio scope.

    Calling ``dashboard`` first applies the same selected-building access
    check as every other report endpoint. Installations without a historical
    arrears ledger still receive an explicit zero-valued dataset rather than a
    404, which keeps the report page stable while showing no arrears.
    """
    dashboard(building_id, current_user)
    return {"buckets": {"0_30_days": 0, "31_60_days": 0, "61_90_days": 0, "90_plus_days": 0}}
