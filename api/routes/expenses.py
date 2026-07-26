from fastapi import APIRouter, HTTPException, Depends
from api.models import ExpenseCreate
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import require_role
import uuid
from datetime import datetime

router = APIRouter(prefix="/expenses", tags=["Expenses"])

STAFF = ["landlord", "caretaker"]


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
        e_copy["building_name"] = bldg.get("name", "N/A")
        results.append(e_copy)

    return {"expenses": results}


@router.post("")
def create_expense(req: ExpenseCreate, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    new_expense = {
        "id": str(uuid.uuid4()),
        "building_id": req.building_id,
        "category": str(req.category)[:100],
        "amount": req.amount,
        "date": req.date,
        "description": str(req.description or "")[:500],
        "receipt_url": req.receipt_url,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    if hasattr(db, "expenses"):
        db.expenses.append(new_expense)
    else:
        try:
            db.table("expenses").insert(new_expense).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to add expense: {str(e)}")

    return {"status": "success", "expense": new_expense}
