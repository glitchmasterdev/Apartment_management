"""
api/routes/demo.py — Demo Mode sandbox environment.

Provides:
  GET  /api/demo/login  — Issue a pre-authenticated demo JWT (no password)
  POST /api/demo/reset  — Wipe and re-seed all demo data
  GET  /api/demo/status — Show demo mode info

All operations are scoped to is_demo=True rows to prevent mixing with real data.
Email and M-Pesa calls are completely mocked in this context.
"""
from fastapi import APIRouter, HTTPException, Response
from api.services.auth_middleware import create_jwt  # reuse the helper
from api.services.supabase_client import get_supabase_client
import uuid
from datetime import datetime

router = APIRouter(prefix="/demo", tags=["Demo Mode"])

# ── Demo landlord identity ────────────────────────────────────────────────────
DEMO_LANDLORD = {
    "id": "demo-landlord-0000-0000-000000000000",
    "full_name": "Demo Landlord",
    "email": "demo@nairobrentals.com",
    "role": "landlord",
    "is_demo": True,
}

# ── Realistic seed data ───────────────────────────────────────────────────────
DEMO_BUILDINGS = [
    {"id": str(uuid.uuid4()), "name": "Kileleshwa Heights", "location": "Kileleshwa, Nairobi", "total_floors": 5, "is_demo": True},
    {"id": str(uuid.uuid4()), "name": "Westlands Court", "location": "Westlands, Nairobi", "total_floors": 4, "is_demo": True},
]

def _make_units():
    b1, b2 = DEMO_BUILDINGS[0]["id"], DEMO_BUILDINGS[1]["id"]
    units = []
    configs = [
        (b1, "A1", 1, 18000, "occupied"), (b1, "A2", 1, 18000, "vacant"),
        (b1, "B1", 2, 20000, "occupied"), (b1, "B2", 2, 20000, "occupied"),
        (b1, "C1", 3, 22000, "occupied"), (b1, "C2", 3, 22000, "vacant"),
        (b1, "D1", 4, 25000, "occupied"), (b1, "D2", 4, 25000, "vacant"),
        (b2, "101", 1, 15000, "occupied"), (b2, "102", 1, 15000, "vacant"),
        (b2, "201", 2, 17000, "occupied"), (b2, "202", 2, 17000, "occupied"),
        (b2, "301", 3, 19000, "vacant"),   (b2, "302", 3, 19000, "occupied"),
        (b2, "401", 4, 21000, "vacant"),
    ]
    for bldg_id, num, floor, rent, status in configs:
        units.append({
            "id": str(uuid.uuid4()),
            "building_id": bldg_id,
            "unit_number": num,
            "floor": floor,
            "rent_amount": rent,
            "deposit_amount": rent,
            "deposit_paid": status == "occupied",
            "status": status,
            "is_active": True,
            "is_demo": True,
        })
    return units

DEMO_UNITS = _make_units()
_OCCUPIED = [u for u in DEMO_UNITS if u["status"] == "occupied"]

DEMO_TENANTS = [
    {"id": str(uuid.uuid4()), "unit_id": _OCCUPIED[0]["id"], "full_name": "Amina Wanjiku", "phone_number": "+254712345678", "email": "amina.demo@example.com", "account_number": "NRB-001-KH-A1", "monthly_rent": _OCCUPIED[0]["rent_amount"], "lease_start_date": "2025-01-01", "is_active": True, "is_approved": True, "password": "demo", "is_demo": True},
    {"id": str(uuid.uuid4()), "unit_id": _OCCUPIED[1]["id"], "full_name": "Brian Kamau", "phone_number": "+254723456789", "email": "brian.demo@example.com", "account_number": "NRB-001-KH-B1", "monthly_rent": _OCCUPIED[1]["rent_amount"], "lease_start_date": "2025-02-01", "is_active": True, "is_approved": True, "password": "demo", "is_demo": True},
    {"id": str(uuid.uuid4()), "unit_id": _OCCUPIED[2]["id"], "full_name": "Christine Njeri", "phone_number": "+254734567890", "email": "christine.demo@example.com", "account_number": "NRB-001-KH-B2", "monthly_rent": _OCCUPIED[2]["rent_amount"], "lease_start_date": "2025-03-01", "is_active": True, "is_approved": True, "password": "demo", "is_demo": True},
    {"id": str(uuid.uuid4()), "unit_id": _OCCUPIED[3]["id"], "full_name": "David Ochieng", "phone_number": "+254745678901", "email": "david.demo@example.com", "account_number": "NRB-001-KH-C1", "monthly_rent": _OCCUPIED[3]["rent_amount"], "lease_start_date": "2025-04-01", "is_active": True, "is_approved": True, "password": "demo", "is_demo": True},
    {"id": str(uuid.uuid4()), "unit_id": _OCCUPIED[4]["id"], "full_name": "Esther Achieng", "phone_number": "+254756789012", "email": "esther.demo@example.com", "account_number": "NRB-001-WC-101", "monthly_rent": _OCCUPIED[4]["rent_amount"], "lease_start_date": "2025-05-01", "is_active": True, "is_approved": True, "password": "demo", "is_demo": True},
]

def _make_payments():
    payments = []
    statuses = ["approved", "approved", "approved", "approved", "pending", "pending", "rejected", "rejected"]
    amounts = [18000, 20000, 20000, 22000, 25000, 15000, 17000, 19000]
    for i, tenant in enumerate(DEMO_TENANTS[:5]):
        for j in range(min(2, len(statuses))):
            idx = i * 2 + j
            payments.append({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant["id"],
                "unit_id": tenant["unit_id"],
                "amount_paid": amounts[idx % len(amounts)],
                "payment_date": f"2026-0{(idx % 6) + 1}-05T10:00:00",
                "mpesa_code": f"QK{idx}DEMO{uuid.uuid4().hex[:4].upper()}",
                "status": statuses[idx % len(statuses)],
                "rejection_reason": "M-Pesa code could not be verified." if statuses[idx % len(statuses)] == "rejected" else None,
                "is_demo": True,
            })
    return payments

DEMO_PAYMENTS = _make_payments()

DEMO_EXPENSES = [
    {"id": str(uuid.uuid4()), "building_id": DEMO_BUILDINGS[0]["id"], "category": "Maintenance", "amount": 12000, "date": "2026-06-15", "description": "Roof repairs — Kileleshwa Heights Block A", "is_demo": True},
    {"id": str(uuid.uuid4()), "building_id": DEMO_BUILDINGS[0]["id"], "category": "Utilities", "amount": 8500, "date": "2026-06-30", "description": "Nairobi Water bill — June 2026", "is_demo": True},
    {"id": str(uuid.uuid4()), "building_id": DEMO_BUILDINGS[1]["id"], "category": "Security", "amount": 15000, "date": "2026-06-01", "description": "Guard services — Westlands Court June", "is_demo": True},
    {"id": str(uuid.uuid4()), "building_id": DEMO_BUILDINGS[1]["id"], "category": "Maintenance", "amount": 3500, "date": "2026-07-02", "description": "Plumbing repair — Unit 201", "is_demo": True},
]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/login")
def demo_login(response: Response):
    """Issue a pre-authenticated demo JWT. No password required."""
    from api.routes.auth import create_jwt, set_auth_cookie
    token = create_jwt(DEMO_LANDLORD)
    set_auth_cookie(response, token)
    return {
        "status": "success",
        "message": "Demo mode active. Signed in as Demo Landlord.",
        "user": DEMO_LANDLORD,
        "token": token,
    }


@router.get("/status")
def demo_status():
    return {
        "demo_mode": True,
        "buildings": len(DEMO_BUILDINGS),
        "units": len(DEMO_UNITS),
        "tenants": len(DEMO_TENANTS),
        "payments": len(DEMO_PAYMENTS),
        "note": "All demo data is isolated. No real emails or M-Pesa calls are made.",
    }


@router.post("/reset")
def demo_reset():
    """Re-seed all demo data. Wipes existing demo rows (is_demo=True) and re-inserts."""
    db = get_supabase_client()

    if hasattr(db, "buildings"):
        # Mock DB: replace demo entries in-memory
        db.buildings = [b for b in db.buildings if not b.get("is_demo")] + DEMO_BUILDINGS
        db.units = [u for u in db.units if not u.get("is_demo")] + DEMO_UNITS
        db.tenants = [t for t in db.tenants if not t.get("is_demo")] + DEMO_TENANTS
        db.payments = [p for p in db.payments if not p.get("is_demo")] + DEMO_PAYMENTS
        db.expenses = [e for e in db.expenses if not e.get("is_demo")] + DEMO_EXPENSES
    else:
        try:
            # Real Supabase: delete then insert
            for table, rows in [
                ("expenses", DEMO_EXPENSES), ("payments", DEMO_PAYMENTS),
                ("tenants", DEMO_TENANTS), ("units", DEMO_UNITS), ("buildings", DEMO_BUILDINGS),
            ]:
                try:
                    db.table(table).delete().eq("is_demo", True).execute()
                except Exception:
                    pass
            for table, rows in [
                ("buildings", DEMO_BUILDINGS), ("units", DEMO_UNITS),
                ("tenants", DEMO_TENANTS), ("payments", DEMO_PAYMENTS), ("expenses", DEMO_EXPENSES),
            ]:
                try:
                    db.table(table).insert(rows).execute()
                except Exception as e:
                    pass  # Best-effort: continue even if some inserts fail
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Demo reset failed: {str(e)}")

    return {
        "status": "success",
        "message": "Demo data reset successfully.",
        "seeded": {
            "buildings": len(DEMO_BUILDINGS),
            "units": len(DEMO_UNITS),
            "tenants": len(DEMO_TENANTS),
            "payments": len(DEMO_PAYMENTS),
            "expenses": len(DEMO_EXPENSES),
        },
    }
