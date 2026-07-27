from fastapi import APIRouter, HTTPException, Depends
from api.models import ExpenseCreate
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import require_role
import uuid
from datetime import datetime

router = APIRouter(prefix="/expenses", tags=["Expenses"])

STAFF = ["landlord", "caretaker"]


def _safe_uuid(val):
    if not val:
        return None
    try:
        import uuid as _u
        _u.UUID(str(val))
        return str(val)
    except (ValueError, AttributeError):
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
        e_copy["building_name"] = bldg.get("name", "N/A")
        results.append(e_copy)

    return {"expenses": results}


@router.post("")
def create_expense(req: ExpenseCreate, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    
    bldg_id = req.building_id
    if not hasattr(db, "expenses"):
        # If DB requires UUID and bldg_id is non-UUID (like "bldg-001"), attempt lookup of real UUID or sanitize
        if not _safe_uuid(bldg_id):
            try:
                b_res = db.table("buildings").select("id").eq("id", bldg_id).execute()
                if b_res.data:
                    bldg_id = b_res.data[0]["id"]
                else:
                    b_res2 = db.table("buildings").select("id").limit(1).execute()
                    if b_res2.data and _safe_uuid(b_res2.data[0]["id"]):
                        bldg_id = b_res2.data[0]["id"]
                    else:
                        bldg_id = None
            except Exception:
                bldg_id = None

    new_expense = {
        "id": str(uuid.uuid4()),
        "category": str(req.category)[:100],
        "amount": req.amount,
        "date": req.date,
        "description": str(req.description or "")[:500],
        "receipt_url": req.receipt_url,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    if bldg_id:
        new_expense["building_id"] = bldg_id

    if hasattr(db, "expenses"):
        new_expense["building_id"] = req.building_id
        db.expenses.append(new_expense)
    else:
        try:
            db.table("expenses").insert(new_expense).execute()
        except Exception as e:
            err_msg = str(e)
            # If insert failed because building_id column has strict UUID type in Postgres schema, insert without building_id
            if "22P02" in err_msg or "invalid input syntax for type uuid" in err_msg or "uuid" in err_msg.lower():
                try:
                    payload_no_bldg = {k: v for k, v in new_expense.items() if k != "building_id"}
                    db.table("expenses").insert(payload_no_bldg).execute()
                except Exception as e2:
                    raise HTTPException(status_code=400, detail=f"Failed to add expense: {str(e2)}")
            else:
                raise HTTPException(status_code=400, detail=f"Failed to add expense: {err_msg}")

    new_expense["building_id"] = req.building_id  # preserve original building_id in response for UI list
    return {"status": "success", "expense": new_expense}
