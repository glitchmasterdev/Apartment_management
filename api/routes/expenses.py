from fastapi import APIRouter, HTTPException, Depends
from api.models import ExpenseCreate
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import require_role
import uuid
from datetime import datetime

router = APIRouter(prefix="/expenses", tags=["Expenses"])

STAFF = ["landlord", "caretaker"]


def _to_uuid(val: str) -> str:
    """Converts any building ID string (e.g. 'bldg-001' or an existing UUID) into a valid RFC UUID string for PostgreSQL."""
    if not val:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, "default_building"))
    try:
        uuid.UUID(str(val))
        return str(val)
    except (ValueError, AttributeError):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(val)))


@router.get("")
def get_expenses(building_id: str = None, current_user: dict = Depends(require_role(STAFF))):
    db = get_supabase_client()
    try:
        expenses = db.expenses if hasattr(db, "expenses") else db.table("expenses").select("*").execute().data
        buildings = db.buildings if hasattr(db, "buildings") else db.table("buildings").select("*").execute().data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load expenses: {str(e)}")

    results = []
    target_uuid = _to_uuid(building_id) if building_id else None

    for e in expenses:
        e_bldg = e.get("building_id")
        if building_id and e_bldg != building_id and e_bldg != target_uuid:
            continue

        bldg = next(
            (b for b in buildings if b.get("id") == e_bldg or _to_uuid(b.get("id")) == e_bldg or b.get("id") == building_id),
            {}
        )
        e_copy = dict(e)
        e_copy["building_name"] = bldg.get("name", "N/A")
        results.append(e_copy)

    return {"expenses": results}


@router.post("")
def create_expense(req: ExpenseCreate, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    valid_bldg_uuid = _to_uuid(req.building_id)

    new_expense = {
        "id": str(uuid.uuid4()),
        "building_id": valid_bldg_uuid,
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
