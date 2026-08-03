"""
auth.py â€” Authentication routes: register, login, logout, pending tenants,
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
import logging

router = APIRouter(prefix="/auth", tags=["Auth"])

# â”€â”€ Password Hashing (Built-in hashlib pbkdf2_hmac) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', plain.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"pbkdf2:{salt}:{key}"

def verify_password(plain: str, stored: str) -> bool:
    if not stored:
        return False
    # If stored in PBKDF2 format
    if stored.startswith("pbkdf2:"):
        try:
            _, salt, key = stored.split(":", 2)
            new_key = hashlib.pbkdf2_hmac('sha256', plain.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
            return secrets.compare_digest(new_key, key)
        except Exception:
            return False
    # Backward-compatibility fallback: legacy plain-text comparison
    return secrets.compare_digest(plain, stored)

# â”€â”€ JWT helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

# Staff credentials are never seeded in source control. Bootstrap accounts through /landlord/signup.
_SEEDED_STAFF = {}  # Compatibility only; intentionally credential-free.

# â”€â”€ Password validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
    if not re.search(r"[A-Za-z]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one letter.")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number.")


# â”€â”€ REGISTER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        "password_hash": hashed,
        "account_number": "PENDING",
        "is_active": False,
        "is_approved": False,
        "email_verified": False,
    }

    if hasattr(db, "tenants"):
        # In-memory mock client
        if any(t.get("email", "").lower() == req.email.strip().lower() for t in db.tenants):
            raise HTTPException(status_code=400, detail="This email address is already registered. Please sign in.")
        db.tenants.append(new_tenant)
    else:
        # Real Supabase DB - direct insert relying on email UNIQUE constraint
        try:
            db.table("tenants").insert(new_tenant).execute()
        except Exception:
            raise HTTPException(status_code=400, detail="Unable to create the account. Check the details and try again.")

    verification_token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    verification = {"verification_token": verification_token, "verification_token_expires": expires_at}
    if hasattr(db, "tenants"):
        new_tenant.update(verification)
    else:
        try:
            db.table("tenants").update(verification).eq("id", user_id).execute()
        except Exception:
            logging.exception("Unable to store verification token")
    app_url = os.getenv("APP_URL", "https://apartment-management-lime.vercel.app")
    from api.services.email import send_email
    send_email(req.email.strip().lower(), "Verify your Apartment Management email", f"<p>Welcome, {req.full_name}.</p><p><a href='{app_url}/verify-email.html?token={verification_token}'>Verify your email address</a>. This link expires in 24 hours.</p>")
    profile = {"id": user_id, "full_name": req.full_name, "role": "tenant", "email": req.email, "email_verified": False, "is_approved": False}
    token = create_jwt(profile)
    set_auth_cookie(response, token)

    return {
        "status": "success",
        "message": "Account created. Awaiting landlord approval.",
        "user": profile,
    }


# â”€â”€ LOGIN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # 1. Check dynamic landlords table in database
    landlord_user = None
    if hasattr(db, "landlords"):
        landlord_user = next((l for l in db.landlords if l.get("email") == req.email.strip().lower()), None)
    else:
        try:
            res_l = db.table("landlords").select("*").eq("email", req.email.strip().lower()).execute()
            if res_l.data and len(res_l.data) > 0:
                landlord_user = res_l.data[0]
        except Exception:
            pass

    if landlord_user:
        if not verify_password(req.password, landlord_user.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        profile = {
            "id": landlord_user.get("id"),
            "full_name": landlord_user.get("name"),
            "email": landlord_user.get("email"),
            "phone_number": landlord_user.get("contact", ""),
            "role": "landlord",
        }
        check_portal_role(profile["role"])
        token = create_jwt(profile)
        set_auth_cookie(response, token)
        return {"status": "success", "message": "Login successful", "user": profile}

    # 1b. Check dynamic caretakers table in database
    caretaker_user = None
    if hasattr(db, "caretakers"):
        caretaker_user = next((c for c in db.caretakers if c.get("email") == req.email.strip().lower()), None)
    else:
        try:
            res_c = db.table("caretakers").select("*").eq("email", req.email.strip().lower()).execute()
            if res_c.data and len(res_c.data) > 0:
                caretaker_user = res_c.data[0]
        except Exception:
            pass

    if caretaker_user:
        if not verify_password(req.password, caretaker_user.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        profile = {
            "id": caretaker_user.get("id"),
            "full_name": caretaker_user.get("name"),
            "email": caretaker_user.get("email"),
            "phone_number": caretaker_user.get("contact", ""),
            "role": "caretaker",
        }
        check_portal_role(profile["role"])
        token = create_jwt(profile)
        set_auth_cookie(response, token)
        return {"status": "success", "message": "Login successful", "user": profile}

    # 2. Check seeded staff accounts (fallback)
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
        return {"status": "success", "message": "Login successful", "user": profile}

    # Check mock db tenants
    if hasattr(db, "tenants"):
        tenant = next((t for t in db.tenants if t.get("email") == req.email), None)
        if tenant:
            stored_pw = tenant.get("password_hash", "")
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
            return {"status": "success", "message": "Login successful", "user": profile}
    else:
        # Real Supabase DB
        try:
            res = db.table("tenants").select("*").eq("email", req.email.strip().lower()).execute()
            if res.data:
                tenant = res.data[0]
                stored_pw = tenant.get("password_hash") or tenant.get("password") or ""
                if not verify_password(req.password, stored_pw):
                    raise HTTPException(status_code=401, detail="Invalid email or password.")
                # Auto-upgrade plain-text password to PBKDF2 hash on successful login
                if stored_pw and not stored_pw.startswith("pbkdf2:"):
                    try:
                        db.table("tenants").update({"password_hash": hash_password(req.password)}).eq("id", tenant["id"]).execute()
                    except Exception:
                        pass
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
                return {"status": "success", "message": "Login successful", "user": profile}
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=503, detail="Sign-in is temporarily unavailable. Please try again shortly.")

    raise HTTPException(status_code=401, detail="Invalid email or password.")


# â”€â”€ LOGOUT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("nrb_token", path="/")
    return {"status": "success", "message": "Logged out."}


@router.post("/change-password")
def change_password(payload: dict, current_user: dict = Depends(get_current_user)):
    """Change the signed-in user's password after verifying the current one."""
    current_password = str(payload.get("current_password") or "")
    new_password = str(payload.get("new_password") or "")
    if not current_password:
        raise HTTPException(status_code=400, detail="Current password is required.")
    validate_password(new_password)

    role = current_user.get("role")
    table_by_role = {"landlord": "landlords", "caretaker": "caretakers", "tenant": "tenants"}
    table = table_by_role.get(role)
    if not table:
        raise HTTPException(status_code=403, detail="This account cannot change its password here.")

    db = get_supabase_client()
    try:
        if hasattr(db, table):
            accounts = getattr(db, table)
            account = next((row for row in accounts if str(row.get("id")) == str(current_user.get("id"))), None)
            if not account:
                raise HTTPException(status_code=404, detail="Account not found.")
            stored_password = account.get("password_hash") or account.get("password") or ""
            if not verify_password(current_password, stored_password):
                raise HTTPException(status_code=401, detail="Current password is incorrect.")
            account["password_hash"] = hash_password(new_password)
            account.pop("password", None)
        else:
            rows = db.table(table).select("id,password_hash").eq("id", current_user["id"]).limit(1).execute().data
            if not rows:
                raise HTTPException(status_code=404, detail="Account not found.")
            stored_password = rows[0].get("password_hash") or ""
            if not verify_password(current_password, stored_password):
                raise HTTPException(status_code=401, detail="Current password is incorrect.")
            db.table(table).update({"password_hash": hash_password(new_password)}).eq("id", current_user["id"]).execute()
        return {"status": "success", "message": "Password changed successfully."}
    except HTTPException:
        raise
    except Exception:
        logging.exception("password_change_failed", extra={"role": role})
        raise HTTPException(status_code=503, detail="Password change is temporarily unavailable. Please try again.")


# â”€â”€ PENDING TENANTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.get("/pending-tenants")
def get_pending_tenants(current_user: dict = Depends(require_role(["landlord", "caretaker"]))):
    db = get_supabase_client()
    if hasattr(db, "tenants"):
        pending = [t for t in db.tenants if not t.get("is_approved", True)]
        return {"tenants": [{k: v for k, v in t.items() if k not in ("password", "password_hash")} for t in pending]}
    try:
        # Include legacy registrations where approval was never explicitly
        # written. A strict `.eq(false)` query hid those valid pending tenants.
        res = db.table("tenants").select("*").execute()
        pending = [t for t in (res.data or []) if not t.get("is_approved")]
        return {"tenants": [{k: v for k, v in t.items() if k != "password"} for t in pending]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load pending tenants: {str(e)}")


# â”€â”€ APPROVE TENANT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€ REJECT TENANT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€ FORGOT PASSWORD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    # Search every account table and retain its name for the reset update.
    user_table = None
    if hasattr(db, "tenants"):
        for table in ("tenants", "landlords", "caretakers"):
            if any(row.get("email", "").lower() == email for row in getattr(db, table, [])):
                user_table = table
                break
    else:
        for table in ("tenants", "landlords", "caretakers"):
            try:
                if db.table(table).select("id").eq("email", email).execute().data:
                    user_table = table
                    break
            except Exception:
                continue

    # If email not found, return generic message without sending or storing anything
    if not user_table:
        return _GENERIC_RESPONSE

    # Generate token and persist to Supabase (survives cold starts)
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

    try:
        if not hasattr(db, "tenants"):
            db.table("password_reset_tokens").insert({
                "token": token,
                "email": email,
                "user_table": user_table,
                "expires_at": expires_at,
                "used": False,
            }).execute()
    except Exception:
        # If token storage fails, return generic message â€” don't send a broken link
        return _GENERIC_RESPONSE

    app_url = os.getenv("APP_URL", "https://apartment-management-lime.vercel.app")
    reset_link = f"{app_url}/reset-password.html?token={token}"

    from api.services.email import send_email
    if not send_email(
        email,
        "Reset your Apartment Management password",
        f"<p>Click the link below to reset your password. It expires in 30 minutes.</p><p><a href='{reset_link}'>{reset_link}</a></p>",
    ):
        logging.error("Password reset email delivery failed for %s", email)

    return _GENERIC_RESPONSE


@router.post("/reset-password")
def reset_password(req: dict):
    token = req.get("token", "")
    new_password = req.get("new_password", "")
    validate_password(new_password)

    db = get_supabase_client()

    # Fetch and validate the token from Supabase
    if hasattr(db, "tenants"):
        # Mock DB fallback â€” token won't persist but gracefully handled
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
        db.table(entry.get("user_table", "tenants")).update({"password_hash": hashed}).eq("email", entry["email"]).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Password reset is temporarily unavailable. Please try again.")

    return {"status": "success", "message": "Password reset successfully. You can now sign in."}


# â”€â”€ SETUP DB (one-time schema migration) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@router.get("/verify-email")
def verify_email(token: str):
    db = get_supabase_client()
    now = datetime.now(timezone.utc)
    if hasattr(db, "tenants"):
        tenant = next((item for item in db.tenants if item.get("verification_token") == token), None)
        if not tenant: raise HTTPException(400, "Verification link is invalid or expired.")
        expires = datetime.fromisoformat(tenant["verification_token_expires"].replace("Z", "+00:00"))
        if now > expires: raise HTTPException(400, "Verification link has expired.")
        tenant.update({"email_verified": True, "verification_token": None, "verification_token_expires": None})
    else:
        rows = db.table("tenants").select("*").eq("verification_token", token).execute().data
        if not rows: raise HTTPException(400, "Verification link is invalid or expired.")
        expires = datetime.fromisoformat(rows[0]["verification_token_expires"].replace("Z", "+00:00"))
        if now > expires: raise HTTPException(400, "Verification link has expired.")
        db.table("tenants").update({"email_verified": True, "verification_token": None, "verification_token_expires": None}).eq("id", rows[0]["id"]).execute()
    return {"status": "success", "message": "Your email has been verified. Your landlord can now approve your account."}

@router.post("/test-email")
def test_email(user: dict = Depends(require_role(["landlord"]))):
    from api.services.email import send_email
    if not send_email(user["email"], "Apartment Management email test", "<p>Your email delivery configuration is working.</p>"):
        raise HTTPException(503, "Email delivery could not be confirmed.")
    return {"status": "success", "message": "Test email submitted for delivery."}

@router.post("/setup-db")
def setup_database(current_user: dict = Depends(require_role(["landlord"]))):
    import os
    results = []
    url = os.getenv("SUPABASE_URL", "")
    key = ""  # Service-role access is prohibited for application requests.
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
