"""
auth.py — Authentication routes: register, login, logout, pending tenants,
approve/reject tenant, forgot/reset password.

Security model:
  - Passwords hashed with pbkdf2_hmac (built-in hashlib, no extra deps)
  - Auth tokens are real signed JWTs (python-jose), 8-hour expiry
  - JWT set as HttpOnly, Secure, SameSite=Strict cookie on login
  - Public registration is TENANTS ONLY (enforced server-side)
  - Password reset tokens persisted in Supabase (survives Vercel cold starts)
  - Reset tokens expire in 30 minutes and are single-use
"""
from fastapi import APIRouter, HTTPException, Depends, Response, Request
from api.models import UserRegisterRequest, UserLoginRequest
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import get_current_user, require_role, SECRET_KEY, ALGORITHM
import jwt
import hashlib
import uuid
import re
import os
import secrets
from datetime import datetime, timedelta, timezone
import resend

router = APIRouter(prefix="/auth", tags=["Auth"])

# ── Password Hashing (Built-in hashlib pbkdf2_hmac) ─────────────────────────
def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', plain.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"pbkdf2:{salt}:{key}"

def verify_password(plain: str, stored: str) -> bool:
    if not stored:
        return False
    # Support legacy plain-text stored passwords
    if not stored.startswith("pbkdf2:"):
        return plain == stored
    try:
        _, salt, key = stored.split(":", 2)
        new_key = hashlib.pbkdf2_hmac('sha256', plain.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        return secrets.compare_digest(new_key, key)
    except Exception:
        return False

# ── JWT helpers ──────────────────────────────────────────────────────────────
JWT_EXPIRY_HOURS = 8

def create_jwt(payload: dict) -> str:
    data = payload.copy()
    data["exp"] = datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key="nrb_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=JWT_EXPIRY_HOURS * 3600,
        path="/",
    )

# ── Seeded staff accounts ────────────────────────────────────────────────────
# Primary landlord and caretaker accounts for this platform.
# To change: update email/password here, push to GitHub → Vercel redeploys automatically.
_SEEDED_STAFF = {
    "billionare081@gmail.com": {
        "id": "00000000-0000-0000-0000-000000000001",
        "full_name": "Landlord Admin",
        "email": "billionare081@gmail.com",
        "phone_number": "+254700000001",
        "role": "landlord",
        "password_hash": hash_password("Nairobi@2026"),
    },
    "caretaker01@gmail.com": {
        "id": "00000000-0000-0000-0000-000000000002",
        "full_name": "Caretaker Admin",
        "email": "caretaker01@gmail.com",
        "phone_number": "+254700000002",
        "role": "caretaker",
        "password_hash": hash_password("caretaker01"),
    },
}

# ── Password validation ──────────────────────────────────────────────────────
def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
    if not re.search(r"[A-Za-z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one letter.")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number.")


# ── REGISTER ─────────────────────────────────────────────────────────────────
@router.post("/register")
def register(req: UserRegisterRequest, response: Response):
    db = get_supabase_client()
    validate_password(req.password)

    # SECURITY: Public signup is TENANTS ONLY
    if req.role and req.role.lower() in ("landlord", "caretaker", "admin", "staff"):
        raise HTTPException(
            status_code=403,
            detail="Staff accounts cannot be self-registered. Contact the platform administrator.",
        )
    req.role = "tenant"

    user_id = str(uuid.uuid4())
    hashed = hash_password(req.password)

    new_tenant = {
        "id": user_id,
        "full_name": req.full_name,
        "phone_number": getattr(req, "phone_number", "") or "",
        "email": req.email.strip().lower(),
        "password": hashed,
        "account_number": "PENDING",
        "is_active": False,
        "is_approved": False,
    }

    if hasattr(db, "tenants"):
        if any(t.get("email", "").lower() == req.email.lower() for t in db.tenants):
            raise HTTPException(status_code=400, detail="This email address is already registered. Please sign in.")
        db.tenants.append(new_tenant)
    else:
        # Check if tenant with this email already exists in Supabase
        try:
            existing = db.table("tenants").select("id").eq("email", req.email.strip().lower()).execute()
            if existing.data and len(existing.data) > 0:
                raise HTTPException(status_code=400, detail="This email address is already registered. Please sign in.")
        except HTTPException:
            raise
        except Exception:
            pass

        try:
            db.table("tenants").insert(new_tenant).execute()
        except Exception as e:
            err = str(e)
            if "23505" in err or "unique constraint" in err:
                raise HTTPException(status_code=400, detail="This email address is already registered. Please sign in.")
            raise HTTPException(status_code=400, detail=f"Database insert error: {err}")

    profile = {"id": user_id, "full_name": req.full_name, "role": "tenant", "email": req.email}
    token = create_jwt(profile)
    set_auth_cookie(response, token)

    return {
        "status": "success",
        "message": "Account created. Awaiting landlord approval.",
        "user": profile,
        "token": token,
    }


# ── LOGIN ────────────────────────────────────────────────────────────────────
@router.post("/login")
def login(req: UserLoginRequest, response: Response):
    db = get_supabase_client()

    def check_portal_role(profile_role: str):
        if not req.expected_role:
            return
        exp = req.expected_role.lower()
        if exp in ("staff", "landlord", "caretaker"):
            if profile_role not in ("landlord", "caretaker"):
                raise HTTPException(
                    status_code=403,
                    detail="Access denied. Tenant accounts must sign in via the Tenant Portal.",
                )
        elif exp == "tenant":
            if profile_role != "tenant":
                raise HTTPException(
                    status_code=403,
                    detail="Access denied. Staff accounts must sign in via the Staff Portal.",
                )

    # Check seeded staff accounts
    if req.email in _SEEDED_STAFF:
        staff = _SEEDED_STAFF[req.email]
        if not verify_password(req.password, staff["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        profile = {
            "id": staff["id"],
            "full_name": staff["full_name"],
            "email": staff["email"],
            "phone_number": staff.get("phone_number", ""),
            "role": staff["role"],
        }
        check_portal_role(profile["role"])
        token = create_jwt(profile)
        set_auth_cookie(response, token)
        return {"status": "success", "message": "Login successful", "user": profile, "token": token}

    # Check mock db tenants
    if hasattr(db, "tenants"):
        tenant = next((t for t in db.tenants if t.get("email") == req.email), None)
        if tenant:
            stored_pw = tenant.get("password", "")
            if not verify_password(req.password, stored_pw):
                raise HTTPException(status_code=401, detail="Invalid email or password.")
            if not tenant.get("is_approved", True):
                raise HTTPException(status_code=403, detail="Your tenant account is pending approval by the landlord or caretaker. You will gain access once approved.")
            profile = {
                "id": tenant["id"],
                "full_name": tenant["full_name"],
                "email": tenant["email"],
                "phone_number": tenant.get("phone_number", ""),
                "role": "tenant",
                "unit_id": tenant.get("unit_id"),
                "account_number": tenant.get("account_number"),
                "monthly_rent": tenant.get("monthly_rent"),
            }
            check_portal_role(profile["role"])
            token = create_jwt(profile)
            set_auth_cookie(response, token)
            return {"status": "success", "message": "Login successful", "user": profile, "token": token}
    else:
        # Real Supabase DB
        try:
            res = db.table("tenants").select("*").eq("email", req.email).execute()
            if res.data:
                tenant = res.data[0]
                stored_pw = tenant.get("password", "")
                if not verify_password(req.password, stored_pw):
                    raise HTTPException(status_code=401, detail="Invalid email or password.")
                if not tenant.get("is_approved", True):
                    raise HTTPException(status_code=403, detail="Your tenant account is pending approval by the landlord or caretaker. You will gain access once approved.")
                profile = {
                    "id": tenant["id"],
                    "full_name": tenant["full_name"],
                    "email": tenant["email"],
                    "phone_number": tenant.get("phone_number", ""),
                    "role": "tenant",
                    "unit_id": tenant.get("unit_id"),
                    "account_number": tenant.get("account_number"),
                    "monthly_rent": tenant.get("monthly_rent"),
                }
                check_portal_role(profile["role"])
                token = create_jwt(profile)
                set_auth_cookie(response, token)
                return {"status": "success", "message": "Login successful", "user": profile, "token": token}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")

    raise HTTPException(status_code=401, detail="Invalid email or password.")


# ── LOGOUT ───────────────────────────────────────────────────────────────────
@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("nrb_token", path="/")
    return {"status": "success", "message": "Logged out."}


# ── PENDING TENANTS ──────────────────────────────────────────────────────────
@router.get("/pending-tenants")
def get_pending_tenants(current_user: dict = Depends(require_role(["landlord", "caretaker"]))):
    db = get_supabase_client()
    if hasattr(db, "tenants"):
        pending = [t for t in db.tenants if not t.get("is_approved", True)]
        return {"tenants": [{k: v for k, v in t.items() if k != "password"} for t in pending]}
    try:
        res = db.table("tenants").select("*").eq("is_approved", False).execute()
        return {"tenants": [{k: v for k, v in t.items() if k != "password"} for t in res.data]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load pending tenants: {str(e)}")


# ── APPROVE TENANT ───────────────────────────────────────────────────────────
@router.post("/approve-tenant/{tenant_id}")
def approve_tenant(
    tenant_id: str,
    payload: dict,
    current_user: dict = Depends(require_role(["landlord"])),
):
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
        unit = next((u for u in db.units if u.get("id") == unit_id), None)
        if not unit:
            raise HTTPException(status_code=404, detail="Unit not found")

        from api.services.ledger import generate_account_number
        from api.services.email import send_welcome_email
        buildings = db.buildings
        bldg = next((b for b in buildings if b.get("id") == unit.get("building_id")), {})
        account_number = generate_account_number("001", bldg.get("name", "BLDG"), unit.get("unit_number", "101"))

        tenant.update({"unit_id": unit_id, "monthly_rent": monthly_rent, "lease_start_date": lease_start,
                       "account_number": account_number, "is_approved": True, "is_active": True})
        unit["status"] = "occupied"
        send_welcome_email(tenant_email=tenant.get("email"), tenant_name=tenant.get("full_name"),
                           account_number=account_number, paybill="247247", due_date="5th of every month")
        return {"status": "success", "message": f"Tenant {tenant.get('full_name')} approved."}
    else:
        try:
            t_res = db.table("tenants").select("*").eq("id", tenant_id).execute()
            if not t_res.data:
                raise HTTPException(status_code=404, detail="Tenant not found")
            tenant = t_res.data[0]
            u_res = db.table("units").select("*").eq("id", unit_id).execute()
            if not u_res.data:
                raise HTTPException(status_code=404, detail="Unit not found")
            unit = u_res.data[0]
            from api.services.ledger import generate_account_number
            from api.services.email import send_welcome_email
            b_res = db.table("buildings").select("*").eq("id", unit.get("building_id", "")).execute()
            bldg_name = b_res.data[0].get("name", "BLDG") if b_res.data else "BLDG"
            account_number = generate_account_number("001", bldg_name, unit.get("unit_number", "101"))
            update_payload = {"unit_id": unit_id, "monthly_rent": monthly_rent, "account_number": account_number,
                              "is_approved": True, "is_active": True}
            if lease_start:
                update_payload["lease_start_date"] = lease_start
            db.table("tenants").update(update_payload).eq("id", tenant_id).execute()
            db.table("units").update({"status": "occupied"}).eq("id", unit_id).execute()
            send_welcome_email(tenant_email=tenant.get("email"), tenant_name=tenant.get("full_name"),
                               account_number=account_number, paybill="247247", due_date="5th of every month")
            return {"status": "success", "message": f"Tenant {tenant.get('full_name')} approved."}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to approve tenant: {str(e)}")


# ── REJECT TENANT ────────────────────────────────────────────────────────────
@router.post("/reject-tenant/{tenant_id}")
def reject_tenant(tenant_id: str, current_user: dict = Depends(require_role(["landlord"]))):
    db = get_supabase_client()
    if hasattr(db, "tenants"):
        tenant = next((t for t in db.tenants if t.get("id") == tenant_id), None)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        db.tenants.remove(tenant)
        return {"status": "success", "message": "Tenant registration rejected."}
    else:
        try:
            db.table("tenants").delete().eq("id", tenant_id).execute()
            return {"status": "success", "message": "Tenant registration rejected."}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to reject tenant: {str(e)}")


# ── FORGOT PASSWORD ───────────────────────────────────────────────────────────
@router.post("/forgot-password")
def forgot_password(req: dict):
    """
    Security notes:
    - Always returns the same generic message regardless of whether the email exists
      (prevents user enumeration).
    - Only sends an email and stores a token if the email is actually in the DB.
    - Tokens stored in Supabase so they survive Vercel serverless cold starts.
    """
    email = req.get("email", "").strip().lower()
    _GENERIC_RESPONSE = {"status": "success", "message": "If that email is registered, a reset link has been sent."}

    if not email:
        return _GENERIC_RESPONSE

    db = get_supabase_client()

    # Check if this email belongs to a real tenant (mock or real DB)
    email_exists = False
    if hasattr(db, "tenants"):
        email_exists = any(t.get("email") == email for t in db.tenants)
    else:
        try:
            res = db.table("tenants").select("id").eq("email", email).execute()
            email_exists = bool(res.data)
        except Exception:
            # On DB error, silently return generic message — don't reveal DB state
            return _GENERIC_RESPONSE

    # If email not found, return generic message without sending or storing anything
    if not email_exists:
        return _GENERIC_RESPONSE

    # Generate token and persist to Supabase (survives cold starts)
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

    try:
        if not hasattr(db, "tenants"):
            db.table("password_reset_tokens").insert({
                "token": token,
                "email": email,
                "expires_at": expires_at,
                "used": False,
            }).execute()
    except Exception:
        # If token storage fails, return generic message — don't send a broken link
        return _GENERIC_RESPONSE

    app_url = os.getenv("APP_URL", "https://apartment-management-lime.vercel.app")
    reset_link = f"{app_url}/reset-password.html?token={token}"

    try:
        resend.api_key = os.getenv("RESEND_API_KEY", "")
        resend.Emails.send({
            "from": "noreply@nairobrentals.com",
            "to": [email],
            "subject": "Reset your Nairobi Rentals password",
            "html": f"<p>Click the link below to reset your password. It expires in 30 minutes.</p><p><a href='{reset_link}'>{reset_link}</a></p>",
        })
    except Exception:
        pass

    return _GENERIC_RESPONSE


@router.post("/reset-password")
def reset_password(req: dict):
    token = req.get("token", "")
    new_password = req.get("new_password", "")
    validate_password(new_password)

    db = get_supabase_client()

    # Fetch and validate the token from Supabase
    if hasattr(db, "tenants"):
        # Mock DB fallback — token won't persist but gracefully handled
        raise HTTPException(status_code=400, detail="Password reset is only available in production mode.")

    try:
        res = db.table("password_reset_tokens").select("*").eq("token", token).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not validate reset token.")

    if not res.data:
        raise HTTPException(status_code=400, detail="Reset link is invalid or has expired.")

    entry = res.data[0]
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromisoformat(entry["expires_at"].replace("Z", "+00:00"))

    if entry.get("used"):
        raise HTTPException(status_code=400, detail="This reset link has already been used.")
    if now > expires_at:
        raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")

    # Mark token as used
    try:
        db.table("password_reset_tokens").update({"used": True}).eq("token", token).execute()
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to invalidate reset token.")

    # Update the password
    hashed = hash_password(new_password)
    try:
        db.table("tenants").update({"password": hashed}).eq("email", entry["email"]).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset password: {str(e)}")

    return {"status": "success", "message": "Password reset successfully. You can now sign in."}


# ── SETUP DB (one-time schema migration) ─────────────────────────────────────
@router.post("/setup-db")
def setup_database(current_user: dict = Depends(require_role(["landlord"]))):
    import os
    results = []
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return {"status": "skipped", "reason": "No Supabase credentials configured."}
    migrations = [
        "ALTER TABLE buildings ALTER COLUMN landlord_id DROP NOT NULL",
        "ALTER TABLE tenants ALTER COLUMN unit_id DROP NOT NULL",
        "ALTER TABLE tenants ALTER COLUMN lease_start_date DROP NOT NULL",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS password TEXT",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT FALSE",
        "ALTER TABLE units ALTER COLUMN building_id DROP NOT NULL",
        "ALTER TABLE expenses ALTER COLUMN building_id DROP NOT NULL",
        "ALTER TABLE expenses ALTER COLUMN building_id TYPE TEXT",
    ]
    try:
        from supabase import create_client
        client = create_client(url, key)
        for sql in migrations:
            try:
                client.rpc("exec_sql", {"query": sql}).execute()
                results.append({"sql": sql[:60], "status": "applied"})
            except Exception as e:
                results.append({"sql": sql[:60], "status": "skipped", "reason": str(e)[:80]})
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    return {"status": "done", "migrations": results}
