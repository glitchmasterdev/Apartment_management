from fastapi import APIRouter, HTTPException, Depends
from api.models import UserRegisterRequest, UserLoginRequest
from api.services.supabase_client import get_supabase_client
import uuid
import re
import os
import secrets
from datetime import datetime, timedelta
import resend


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
            "lease_start_date": None,
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
    else:
        # Check registered tenants in real db
        try:
            res = db.table("tenants").select("*").eq("email", req.email).execute()
            if res.data:
                tenant = res.data[0]
                if tenant.get("password") != req.password:
                    raise HTTPException(status_code=401, detail="Invalid email or password.")
                
                # Enforce approval check
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
        except Exception as e:
            print(f"[Real DB Tenant Login Error]: {e}")
            raise HTTPException(status_code=500, detail="Database connection error during login.")

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

# Global in-memory reset token store (token -> {"email": email, "expires": datetime})
RESET_TOKENS = {}

@router.post("/forgot-password")
def forgot_password(req: dict):
    email = req.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")

    # Check if user exists (DEFAULT_USERS or DB)
    user_exists = False
    matched_key = next((k for k in DEFAULT_USERS if k.lower() == email), None)
    if matched_key:
        user_exists = True
    else:
        db = get_supabase_client()
        if hasattr(db, "tenants"):
            tenant = next((t for t in db.tenants if t.get("email", "").lower() == email), None)
            if tenant:
                user_exists = True
        else:
            try:
                res = db.table("tenants").select("id").eq("email", email).execute()
                if res.data:
                    user_exists = True
            except Exception:
                pass

    if not user_exists:
        # Return success anyway to prevent email enumeration
        return {
            "status": "success",
            "message": "If an account with that email exists, a password reset link has been sent."
        }

    # Generate token
    token = secrets.token_urlsafe(32)
    expiry = datetime.now() + timedelta(minutes=30)
    RESET_TOKENS[token] = {"email": email, "expires": expiry}

    # Build reset link using Vercel app URL or fallback to localhost
    app_url = os.getenv("APP_URL", "http://localhost:8000")
    reset_link = f"{app_url}/reset-password.html?token={token}"

    resend_key = os.getenv("RESEND_API_KEY", "")
    if not resend_key or resend_key == "re_your_api_key_here":
        # Fallback simulator
        print(f"[Password Reset] Simulated reset link for {email}: {reset_link}")
        return {
            "status": "success",
            "message": f"If an account with that email exists, a password reset link has been sent. (Simulated Link: {reset_link})"
        }

    try:
        resend.api_key = resend_key
        # Send transactional email via Resend
        resend.Emails.send({
            "from": "Nairobi Rentals <onboarding@resend.dev>",
            "to": email,
            "subject": "Reset Your Nairobi Rentals Password",
            "html": f"""
            <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #dfd9cd; border-radius: 12px; background-color: #fbf9f4;">
                <h2 style="font-family: serif; color: #1c1a17; font-weight: 300;">Nairobi Rentals</h2>
                <hr style="border: 0; border-top: 1px solid #dfd9cd; margin: 20px 0;" />
                <p style="color: #1c1a17; font-size: 16px;">Hello,</p>
                <p style="color: #1c1a17; font-size: 14px; line-height: 1.5;">We received a request to reset your account password. Click the button below to set a new password:</p>
                <div style="margin: 30px 0; text-align: center;">
                    <a href="{reset_link}" style="background-color: #c2593f; color: white; padding: 12px 24px; text-decoration: none; font-size: 14px; font-weight: 600; border-radius: 50px; display: inline-block;">Reset Password</a>
                </div>
                <p style="color: #1c1a17; font-size: 12px; line-height: 1.5; opacity: 0.6;">This link will expire in 30 minutes. If you did not request a password reset, please ignore this email.</p>
                <hr style="border: 0; border-top: 1px solid #dfd9cd; margin: 20px 0;" />
                <p style="color: #1c1a17; font-size: 11px; text-align: center; opacity: 0.4;">© 2026 Nairobi Rentals. All rights reserved.</p>
            </div>
            """
        })
        return {
            "status": "success",
            "message": "If an account with that email exists, a password reset link has been sent."
        }
    except Exception as e:
        print(f"[Password Reset] Resend exception: {e}")
        return {
            "status": "success",
            "message": f"If an account with that email exists, a password reset link has been sent. (Resend API error, Simulated Link: {reset_link})"
        }

@router.post("/reset-password")
def reset_password(req: dict):
    token = req.get("token", "")
    new_password = req.get("new_password", "")

    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token and new password are required.")

    if token not in RESET_TOKENS:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    token_data = RESET_TOKENS[token]
    if datetime.now() > token_data["expires"]:
        del RESET_TOKENS[token]
        raise HTTPException(status_code=400, detail="Reset token has expired.")

    email = token_data["email"]
    validate_password(new_password)

    # 1. Check DEFAULT_USERS
    matched_key = next((k for k in DEFAULT_USERS if k.lower() == email), None)
    if matched_key:
        DEFAULT_USERS[matched_key]["password"] = new_password
        del RESET_TOKENS[token]
        return {"status": "success", "message": "Password reset successfully."}

    # 2. Check DB / Mock Tenants
    db = get_supabase_client()
    if hasattr(db, "tenants"):
        tenant = next((t for t in db.tenants if t.get("email", "").lower() == email), None)
        if tenant:
            tenant["password"] = new_password
            del RESET_TOKENS[token]
            return {"status": "success", "message": "Password reset successfully."}
    else:
        try:
            db.table("tenants").update({"password": new_password}).eq("email", email).execute()
            del RESET_TOKENS[token]
            return {"status": "success", "message": "Password reset successfully."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")

    raise HTTPException(status_code=404, detail="Account not found.")


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

@router.post("/change-password")
def change_password(req: dict):
    email = req.get("email", "").strip().lower()
    current_password = req.get("current_password", "")
    new_password = req.get("new_password", "")

    if not email or not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Email, current password, and new password are all required.")

    # Validate new password strength
    validate_password(new_password)

    # Check DEFAULT_USERS (landlord / caretaker accounts)
    matched_key = next((k for k in DEFAULT_USERS if k.lower() == email), None)
    if matched_key:
        user = DEFAULT_USERS[matched_key]
        if user["password"] != current_password:
            raise HTTPException(status_code=401, detail="Current password is incorrect.")
        user["password"] = new_password
        return {"status": "success", "message": "Password updated successfully."}

    # Check registered tenants in mock DB
    db = get_supabase_client()
    if hasattr(db, "tenants"):
        tenant = next((t for t in db.tenants if t.get("email", "").lower() == email), None)
        if tenant:
            if tenant.get("password") != current_password:
                raise HTTPException(status_code=401, detail="Current password is incorrect.")
            tenant["password"] = new_password
            return {"status": "success", "message": "Password updated successfully."}

    raise HTTPException(status_code=404, detail="Account not found.")

