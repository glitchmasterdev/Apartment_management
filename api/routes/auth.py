from fastapi import APIRouter, HTTPException, Depends
from api.models import UserRegisterRequest, UserLoginRequest
from api.services.supabase_client import get_supabase_client
import uuid
import re

router = APIRouter(prefix="/auth", tags=["Auth"])

# Default seeded users (email → profile)
DEFAULT_USERS = {
    "landlord01@gmail.com": {
        "id": "landlord-1",
        "full_name": "Landlord Admin",
        "email": "landlord01@gmail.com",
        "phone_number": "+254700000001",
        "role": "landlord",
        "password": "landlord01"
    },
    "caretaker01@gmail.com": {
        "id": "caretaker-1",
        "full_name": "Caretaker Admin",
        "email": "caretaker01@gmail.com",
        "phone_number": "+254700000002",
        "role": "caretaker",
        "password": "caretaker01"
    }
}

def validate_password(password: str):
    """Enforce min 8 chars, must have both letters and numbers."""
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
    if not re.search(r"[A-Za-z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one letter.")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number.")

@router.post("/register")
def register(req: UserRegisterRequest):
    db = get_supabase_client()
    validate_password(req.password)
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    profile = {
        "id": user_id,
        "full_name": req.full_name,
        "role": req.role,
        "email": req.email,
        "phone_number": getattr(req, "phone_number", ""),
    }
    
    # Save tenant to database with pending approval status
    if req.role == "tenant":
        new_tenant = {
            "id": user_id,
            "unit_id": None,
            "full_name": req.full_name,
            "phone_number": getattr(req, "phone_number", ""),
            "email": req.email,
            "password": req.password, # stored for testing simple login
            "account_number": "PENDING",
            "lease_start_date": "",
            "monthly_rent": 0,
            "is_active": False,
            "is_approved": False
        }
        if hasattr(db, "tenants"):
            # Avoid duplicate signups by email
            if any(t.get("email") == req.email for t in db.tenants):
                raise HTTPException(status_code=400, detail="A tenant with this email already exists.")
            db.tenants.append(new_tenant)
        else:
            db.table("tenants").insert(new_tenant).execute()

    paybill_config = {
        "id": f"pay-cfg-{uuid.uuid4().hex[:6]}",
        "landlord_id": user_id,
        "paybill_number": req.paybill_number or "247247",
        "account_reference_format": "LND-{id}-{building}-{unit}"
    }
    return {
        "status": "success",
        "message": "Tenant registration submitted. Awaiting approval by landlord or caretaker.",
        "user": profile,
        "paybill_config": paybill_config,
        "token": f"mock-token-{user_id}"
    }

@router.post("/login")
def login(req: UserLoginRequest):
    db = get_supabase_client()
    # Check default seeded users
    if req.email in DEFAULT_USERS:
        user = DEFAULT_USERS[req.email]
        if req.password != user["password"]:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        return {
            "status": "success",
            "message": "Login successful",
            "user": {
                "id": user["id"],
                "full_name": user["full_name"],
                "email": user["email"],
                "phone_number": user.get("phone_number", ""),
                "role": user["role"]
            },
            "token": f"mock-jwt-{user['id']}"
        }
    # Check registered tenants in mock db
    if hasattr(db, "tenants"):
        tenant = next((t for t in db.tenants if t.get("email") == req.email), None)
        if tenant:
            # Check password if registration set one (for mock testing)
            if "password" in tenant and tenant["password"] != req.password:
                raise HTTPException(status_code=401, detail="Invalid email or password.")
            
            # Enforce landlord/caretaker approval check
            if not tenant.get("is_approved", True):
                raise HTTPException(
                    status_code=403, 
                    detail="Your tenant account is pending approval by the landlord or caretaker. You will gain access once approved."
                )
                
            return {
                "status": "success",
                "message": "Login successful",
                "user": {
                    "id": tenant["id"],
                    "full_name": tenant["full_name"],
                    "email": tenant["email"],
                    "phone_number": tenant.get("phone_number", ""),
                    "role": "tenant",
                    "unit_id": tenant.get("unit_id"),
                    "account_number": tenant.get("account_number"),
                    "monthly_rent": tenant.get("monthly_rent")
                },
                "token": f"mock-jwt-{tenant['id']}"
            }
    raise HTTPException(status_code=401, detail="Invalid email or password.")

@router.get("/pending-tenants")
def get_pending_tenants():
    db = get_supabase_client()
    if hasattr(db, "tenants"):
        pending = [t for t in db.tenants if not t.get("is_approved", True)]
        return {"tenants": pending}
    else:
        res = db.table("tenants").select("*").eq("is_approved", False).execute()
        return {"tenants": res.data}

@router.post("/approve-tenant/{tenant_id}")
def approve_tenant(tenant_id: str, payload: dict):
    db = get_supabase_client()
    unit_id = payload.get("unit_id")
    monthly_rent = payload.get("monthly_rent", 0)
    lease_start = payload.get("lease_start_date", "")

    if not unit_id:
        raise HTTPException(status_code=400, detail="Unit ID is required to approve and assign a tenant.")

    if hasattr(db, "tenants"):
        tenant = next((t for t in db.tenants if t.get("id") == tenant_id), None)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Check unit status
        unit = next((u for u in db.units if u.get("id") == unit_id), None)
        if not unit:
            raise HTTPException(status_code=404, detail="Unit not found")
        
        # Update tenant fields
        from api.services.ledger import generate_account_number
        buildings = db.buildings
        bldg = next((b for b in buildings if b.get("id") == unit.get("building_id")), {})
        bldg_name = bldg.get("name", "BLDG")
        account_number = generate_account_number("001", bldg_name, unit.get("unit_number", "101"))

        tenant["unit_id"] = unit_id
        tenant["monthly_rent"] = monthly_rent
        tenant["lease_start_date"] = lease_start
        tenant["account_number"] = account_number
        tenant["is_approved"] = True
        tenant["is_active"] = True

        unit["status"] = "occupied"

        # Simulating welcome email
        from api.services.email import send_welcome_email
        send_welcome_email(
            tenant_email=tenant.get("email"),
            tenant_name=tenant.get("full_name"),
            account_number=account_number,
            paybill="247247",
            due_date="5th of every month"
        )
        return {"status": "success", "message": f"Tenant {tenant.get('full_name')} approved and assigned to Unit {unit.get('unit_number')}"}
    else:
        # Real Supabase DB transaction (omitted here, handled mock style for this phase)
        return {"status": "success"}

@router.post("/reject-tenant/{tenant_id}")
def reject_tenant(tenant_id: str):
    db = get_supabase_client()
    if hasattr(db, "tenants"):
        tenant = next((t for t in db.tenants if t.get("id") == tenant_id), None)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        db.tenants.remove(tenant)
        return {"status": "success", "message": "Tenant registration rejected and removed."}
    else:
        db.table("tenants").delete().eq("id", tenant_id).execute()
        return {"status": "success"}

@router.post("/forgot-password")
def forgot_password(req: dict):
    email = req.get("email", "")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    # In production, send reset link via SMTP. For now simulate success.
    print(f"[Password Reset] Simulated reset link sent to: {email}")
    return {
        "status": "success",
        "message": f"If an account with {email} exists, a password reset link has been sent."
    }

@router.get("/me")
def get_me():
    return {
        "user": {
            "id": "landlord-1",
            "full_name": "Landlord Admin",
            "email": "landlord01@gmail.com",
            "role": "landlord"
        }
    }
