from fastapi import APIRouter, HTTPException
from api.models import ExpenseCreate
from api.services.supabase_client import get_supabase_client
import uuid

router = APIRouter(prefix="/expenses", tags=["Expenses"])

@router.get("")
def get_expenses(building_id: str = None):
    db = get_supabase_client()
    expenses = db.expenses if hasattr(db, "expenses") else db.table("expenses").select("*").execute().data
    buildings = db.buildings if hasattr(db, "buildings") else db.table("buildings").select("*").execute().data

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
def create_expense(req: ExpenseCreate):
    db = get_supabase_client()
    new_expense = {
        "id": str(uuid.uuid4()),
        "building_id": req.building_id,
        "category": req.category,
        "amount": req.amount,
        "date": req.date,
        "description": req.description,
        "receipt_url": req.receipt_url,
        "created_at": "2026-07-24T12:00:00Z"
    }

    if hasattr(db, "expenses"):
        db.expenses.append(new_expense)
    else:
        db.table("expenses").insert(new_expense).execute()

    return {"status": "success", "expense": new_expense}
