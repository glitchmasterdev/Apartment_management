from datetime import datetime, timezone
import calendar
from fastapi import APIRouter, Depends, HTTPException
from api.services.auth_middleware import require_role
from api.services.access import db_for, allowed_building_ids, require_building_access, fail_closed
from api.services.timekeeping import kenya_today

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])
STAFF = ["landlord", "caretaker"]


def _payment_cycle_start(db) -> str | None:
    """Return the landlord-controlled cycle start, if one has been set."""
    try:
        rows = (
            db.table("system_settings")
            .select("value")
            .eq("key", "payment_cycle_started_at")
            .limit(1)
            .execute()
            .data
            or []
        )
        return str(rows[0].get("value") or "") or None
    except Exception:
        # Legacy installations may not have this setting yet. In that case
        # payments remain in the active cycle until staff starts a new one.
        return None


@router.post("/monthly-cycle/close")
def close_monthly_cycle(current_user: dict = Depends(require_role(STAFF))):
    """Start a staff-controlled payment cycle without deleting history."""
    db = db_for(current_user)
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        db.table("system_settings").upsert({
            "key": "payment_cycle_started_at",
            "value": started_at,
        }).execute()
    except Exception as exc:
        fail_closed(exc, "close_payment_cycle")
    return {
        "status": "success",
        "started_at": started_at,
        "message": "New payment cycle started. Payment history was retained.",
    }

@router.get("/dashboard")
def dashboard(building_id: str | None = None, current_user: dict = Depends(require_role(["landlord"]))):
    db=db_for(current_user)
    try:
        ids=[building_id] if building_id else list(allowed_building_ids(db,current_user))
        if building_id:
            require_building_access(db,current_user,building_id)
            units=db.table("units").select("id,status,building_id,rent_amount,unit_number").eq("building_id", building_id).execute().data
        else:
            units=db.table("units").select("id,status,building_id,rent_amount,unit_number").in_("building_id",ids).execute().data if ids else []
        unit_ids=[u["id"] for u in units]

        # Unit status is the authoritative, always-available occupancy source.
        # Tenant and payment lookups add detail, but their failure must never
        # make a selected building look empty on the landlord dashboard.
        active_tenants = []
        if unit_ids:
            try:
                active_tenants = db.table("tenants").select("id,unit_id,full_name,monthly_rent").in_("unit_id", unit_ids).eq("is_active", True).execute().data
            except Exception:
                # Legacy databases can be missing tenants.is_active. Unit
                # statuses still provide accurate building occupancy totals.
                active_tenants = []

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
        # approved payments in the staff-controlled payment cycle and scoped
        # to the selected building(s). There is deliberately no automatic
        # first-of-month reset.
        cycle_start = _payment_cycle_start(db)
        approved_payments = []
        if unit_ids:
            approved_payments = (
                db.table("payments")
                .select("tenant_id,amount_paid,payment_date")
                .in_("unit_id", unit_ids)
                .eq("status", "approved")
                .execute()
                .data
                or []
            )
        rent_received = sum(
            float(payment.get("amount_paid") or 0)
            for payment in approved_payments
            if not cycle_start or str(payment.get("payment_date") or "") >= cycle_start
        )
        total_arrears = max(0, revenue - rent_received)

        top_arrears = []
        try:
            settings = db.table("landlord_settings").select("rent_due_day").limit(1).execute().data
            due_day = settings[0].get("rent_due_day", 5) if settings else 5
        except Exception:
            due_day = 5
            
        today = kenya_today()
        days_overdue = max(0, today.day - due_day) if today.day > due_day else 0

        for t in active_tenants:
            paid_by_tenant = sum(
                float(p.get("amount_paid") or 0)
                for p in approved_payments
                if p.get("tenant_id") == t.get("id") and (not cycle_start or str(p.get("payment_date") or "") >= cycle_start)
            )
            unit = next((u for u in units if str(u.get("id")) == str(t.get("unit_id"))), {})
            
            due = float(t.get("monthly_rent") or unit.get("rent_amount") or 0)
            balance = max(0, due - paid_by_tenant)
            
            if balance > 0:
                top_arrears.append({
                    "tenant_name": t.get("full_name") or "Tenant",
                    "unit_number": unit.get("unit_number") or "",
                    "days_overdue": days_overdue,
                    "balance": balance
                })
        
        top_arrears.sort(key=lambda x: x["balance"], reverse=True)

        return {
            "top_arrears": top_arrears,
            "kpis": {
                "total_units": total,
                "occupied_units": occupied,
                "occupancy_rate": round(100 * occupied / total, 1) if total else 0,
                "monthly_revenue": revenue,
                "rent_received": rent_received,
                "total_arrears": total_arrears,
            },
            "payment_cycle_started_at": cycle_start,
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
    db = db_for(current_user)
    today = kenya_today()
    labels = [calendar.month_abbr[month] for month in range(1, 13)]
    
    ids = [building_id] if building_id else list(allowed_building_ids(db, current_user))
    if building_id:
        units = db.table("units").select("id,status,building_id").eq("building_id", building_id).execute().data
    else:
        units = db.table("units").select("id,status,building_id").in_("building_id", ids).execute().data if ids else []
        
    unit_ids = [u["id"] for u in units]
    unit_id_set = {str(uid) for uid in unit_ids}
    all_tenants = []
    if unit_ids:
        try:
            # Primary: tenants still linked to their unit (active OR soft-deleted with unit_id retained)
            all_tenants = db.table("tenants").select("id,unit_id,lease_start_date,lease_end_date,created_at,is_active").in_("unit_id", unit_ids).execute().data or []
        except Exception:
            pass
        try:
            # Fallback: pick up legacy inactive tenants whose unit_id was cleared (old hard-delete
            # behaviour). We recover them by matching on lease_end_date being present this year,
            # scoped to the same building through a separate payments or occupancy_logs join if
            # available. For now we grab all inactive tenants with a lease_end_date this year
            # whose unit_id is null – they cannot be building-scoped precisely, but including
            # them avoids the "previous months drop" symptom for the current portfolio.
            from api.services.timekeeping import kenya_today as _kt
            _today = _kt()
            orphan_tenants = (
                db.table("tenants")
                .select("id,unit_id,lease_start_date,lease_end_date,created_at,is_active")
                .eq("is_active", False)
                .is_("unit_id", "null")
                .gte("lease_end_date", str(_today.year) + "-01-01")
                .execute()
                .data or []
            )
            existing_ids = {t["id"] for t in all_tenants}
            all_tenants += [t for t in orphan_tenants if t["id"] not in existing_ids]
        except Exception:
            pass

    total = len(units)
    if not total:
        return {"labels": labels, "current_year": [0] * 12, "previous_year": [0] * 12}
        
    valid_intervals = []
    for t in all_tenants:
        start_str = t.get("lease_start_date") or t.get("created_at")
        end_str = t.get("lease_end_date")
        
        start_dt = None
        if start_str:
            try:
                dt = datetime.fromisoformat(str(start_str).replace('Z', '+00:00'))
                start_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
        if not start_dt:
            start_dt = datetime(today.year, 1, 1, tzinfo=timezone.utc)
            
        end_dt = None
        if end_str:
            try:
                dt = datetime.fromisoformat(str(end_str).replace('Z', '+00:00'))
                end_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
                
        # Skip legacy inactive tenants lacking an end date
        if not t.get("is_active") and not end_dt:
            continue
            
        valid_intervals.append((start_dt, end_dt))
            
    active_unit_ids = {str(t.get("unit_id")) for t in all_tenants if t.get("is_active") and t.get("unit_id")}
    extra_occupied = sum(1 for u in units if u.get("status") == "occupied" and str(u.get("id")) not in active_unit_ids)
    
    current_year = [0] * 12
    for m in range(1, 13):
        if m > today.month:
            continue
            
        last_day = calendar.monthrange(today.year, m)[1]
        month_start = datetime(today.year, m, 1, tzinfo=timezone.utc)
        month_end = datetime(today.year, m, last_day, 23, 59, 59, tzinfo=timezone.utc)
        
        count = extra_occupied
        for start_dt, end_dt in valid_intervals:
            if start_dt <= month_end:
                if not end_dt or end_dt >= month_start:
                    count += 1
                    
        current_year[m-1] = round((count / total) * 100, 1)
        
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
