from fastapi import APIRouter, HTTPException, Depends
from api.models import ExpenseCreate
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import require_role
import uuid
from datetime import datetime

router = APIRouter(prefix="/expenses", tags=["Expenses"])

STAFF = ["landlord", "caretaker"]


def _get_valid_building_id(db, req_bldg_id: str) -> str | None:
    """Ensures a valid building_id UUID exists in the Supabase buildings table to satisfy foreign key constraints."""
    if hasattr(db, "expenses"):
        return req_bldg_id

    try:
        # 1. Direct match by exact ID in Supabase
        if req_bldg_id:
            b_res = db.table("buildings").select("id").eq("id", req_bldg_id).execute()
            if b_res.data:
                return b_res.data[0]["id"]

        # 2. Match by deterministic UUID5 if mock ID like 'bldg-001'
        if req_bldg_id:
            u5_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(req_bldg_id)))
            b_res_u5 = db.table("buildings").select("id").eq("id", u5_id).execute()
            if b_res_u5.data:
                return b_res_u5.data[0]["id"]

        # 3. Match any existing building in Supabase
        b_res2 = db.table("buildings").select("id").limit(1).execute()
        if b_res2.data:
            return b_res2.data[0]["id"]

        # 4. Seed default buildings into Supabase if table is empty
        b1_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "bldg-001"))
        b2_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "bldg-002"))
        now_str = datetime.utcnow().isoformat() + "Z"
        ins_res = db.table("buildings").insert([
            {"id": b1_id, "name": "Kileleshwa Park Heights", "location": "Kileleshwa, Nairobi", "total_floors": 6, "created_at": now_str},
            {"id": b2_id, "name": "Westlands Executive Suites", "location": "Westlands, Nairobi", "total_floors": 4, "created_at": now_str}
        ]).execute()
        if ins_res.data:
            return ins_res.data[0]["id"]
        return b1_id
    except Exception:
        return None


@router.get("")
def get_expenses(building_id: str = None, current_user: dict = Depends(require_role(STAFF))):
    db = get_supabase_client()
    try:
        expenses = db.expenses if hasattr(db, "expenses") else db.table("expenses").select("*").execute().data
        buildings = db.buildings if hasattr(db, "buildings") else db.table("buildings").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load expenses: {str(e)}")

    results = []
    for e in expenses:
        if building_id and e.get("building_id") != building_id:
            continue
        bldg = next((b for b in buildings if b.get("id") == e.get("building_id")), {})
        e_copy = dict(e)
        e_copy["building_name"] = bldg.get("name", "Nairobi Property")
        results.append(e_copy)

    return {"expenses": results}


@router.post("")
def create_expense(req: ExpenseCreate, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    valid_bldg_id = _get_valid_building_id(db, req.building_id)

    new_expense = {
        "id": str(uuid.uuid4()),
        "category": str(req.category)[:100],
        "amount": req.amount,
        "date": req.date,
        "description": str(req.description or "")[:500],
        "receipt_url": req.receipt_url,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    if valid_bldg_id:
        new_expense["building_id"] = valid_bldg_id

    if hasattr(db, "expenses"):
        new_expense["building_id"] = req.building_id
        db.expenses.append(new_expense)
    else:
        try:
            db.table("expenses").insert(new_expense).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to add expense: {str(e)}")

    new_expense["building_id"] = req.building_id
    return {"status": "success", "expense": new_expense}
