from fastapi import APIRouter, HTTPException, Depends
from api.models import ExpenseCreate
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import require_role
import uuid
from datetime import datetime

router = APIRouter(prefix="/expenses", tags=["Expenses"])

STAFF = ["landlord", "caretaker"]


def _is_valid_uuid(val: str) -> bool:
    """Check whether a string is a valid UUID."""
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


def _get_landlord_profile_id(db) -> str | None:
    """Look up the first landlord profile ID from the profiles table."""
    try:
        res = db.table("profiles").select("id").eq("role", "landlord").limit(1).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass
    return None


def _get_valid_building_id(db, req_bldg_id: str) -> str:
    """Ensures a valid building_id UUID exists in the Supabase buildings table.

    Strategy:
      1. If req_bldg_id is already a valid UUID, look it up directly.
      2. Use any existing building in the database.
      3. Auto-seed a default building (with landlord_id from profiles to
         satisfy the foreign key constraint).
    """
    if hasattr(db, "expenses"):
        return req_bldg_id or "bldg-001"

    try:
        # 1. Match by exact UUID if the requested ID is a valid UUID
        if req_bldg_id and _is_valid_uuid(req_bldg_id):
            b_res = db.table("buildings").select("id").eq("id", req_bldg_id).execute()
            if b_res.data:
                return b_res.data[0]["id"]

        # 2. Use any existing building in Supabase
        b_res2 = db.table("buildings").select("id").limit(1).execute()
        if b_res2.data:
            return b_res2.data[0]["id"]

        # 3. Auto-seed a default building with landlord_id from profiles
        bldg_uuid = str(uuid.uuid4())
        new_bldg = {
            "id": bldg_uuid,
            "name": "Kileleshwa Park Heights",
            "location": "Kileleshwa, Nairobi",
            "total_floors": 6,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        # The buildings table has a NOT NULL foreign key landlord_id -> profiles(id)
        landlord_id = _get_landlord_profile_id(db)
        if landlord_id:
            new_bldg["landlord_id"] = landlord_id
        ins_res = db.table("buildings").insert(new_bldg).execute()
        if ins_res.data:
            return ins_res.data[0]["id"]
        return bldg_uuid
    except Exception as exc:
        raise RuntimeError(f"Could not resolve or create a building: {exc}")


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
    try:
        valid_bldg_id = _get_valid_building_id(db, req.building_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    new_expense = {
        "id": str(uuid.uuid4()),
        "building_id": valid_bldg_id,
        "category": str(req.category)[:100],
        "amount": req.amount,
        "date": req.date,
        "description": str(req.description or "")[:500],
        "receipt_url": req.receipt_url,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

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


@router.delete("/{expense_id}")
def delete_expense(expense_id: str, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    try:
        if hasattr(db, "expenses"):
            before = len(db.expenses)
            db.expenses[:] = [e for e in db.expenses if e.get("id") != expense_id]
            if len(db.expenses) == before: raise HTTPException(404, "Expense not found")
        else:
            result = db.table("expenses").delete().eq("id", expense_id).execute()
            if not result.data: raise HTTPException(404, "Expense not found")
        return {"status": "success"}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(400, detail=f"Could not delete expense: {exc}")
