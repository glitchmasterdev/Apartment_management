"""
landlord_auth.py — Dynamic Landlord & Caretaker Account Management Routes.

Endpoints:
  GET  /api/landlord/status          — Returns whether a landlord row exists
  POST /api/landlord/signup          — Bootstrap signup (only if no landlord exists)
  POST /api/landlord/update          — Direct update: verify current password, apply changes immediately
  POST /api/landlord/update-caretaker — Landlord-only: update caretaker email/password/name
  POST /api/landlord/forgot-password  — Send password reset token link to landlord email
  POST /api/landlord/reset-password   — Validate reset token and set new password
  POST /api/landlord/request-change   — (Legacy) Email-confirmation flow (kept for backward compat)
  GET  /api/landlord/confirm-change   — (Legacy) Validate email token and apply changes
"""
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse

from api.models import (
    LandlordSignupRequest,
    LandlordChangeRequest,
    LandlordDirectUpdateRequest,
    CaretakerUpdateRequest,
    LandlordForgotPasswordRequest,
    LandlordResetPasswordRequest,
)
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import require_role, get_current_user
from api.services.email import (
    send_landlord_change_confirmation_email,
    send_landlord_password_reset_email,
)
from api.routes.auth import hash_password, verify_password, create_jwt, _SEEDED_STAFF

router = APIRouter(prefix="/landlord", tags=["Landlord Management"])

STAFF_ROLES = ["landlord", "caretaker"]
LANDLORD_ONLY = ["landlord"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bootstrap_seeded_landlord(db):
    """
    If the landlords table is empty, auto-seed the hardcoded landlord into it.
    This ensures request-change / update always finds an active landlord record.
    Returns the (possibly just-created) landlord record, or None.
    """
    seeded = next(
        (s for s in _SEEDED_STAFF.values() if s.get("role") == "landlord"),
        None
    )
    if not seeded:
        return None

    record = {
        "id": seeded["id"],
        "name": seeded["full_name"],
        "email": seeded["email"],
        "password_hash": seeded["password_hash"],
        "contact": seeded.get("phone_number", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if hasattr(db, "landlords"):
        db.landlords.append(record)
    else:
        try:
            db.table("landlords").insert(record).execute()
        except Exception as e:
            print(f"[Landlord Bootstrap Warning]: {e}")

    # Also update the _SEEDED_STAFF entry so it stays consistent at runtime
    return record


def _get_active_landlord(db):
    """
    Fetches the primary active landlord row.
    Falls back to auto-bootstrapping from _SEEDED_STAFF if the table is empty.
    """
    if hasattr(db, "landlords"):
        if db.landlords:
            return db.landlords[0]
        # Table is empty → bootstrap
        return _bootstrap_seeded_landlord(db)

    try:
        res = db.table("landlords").select("*").limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass

    # Supabase table empty or missing → bootstrap
    return _bootstrap_seeded_landlord(db)


def _get_active_caretaker(db):
    """
    Fetches the primary caretaker record from the caretakers table or _SEEDED_STAFF.
    """
    if hasattr(db, "caretakers"):
        if db.caretakers:
            return db.caretakers[0]
    else:
        try:
            res = db.table("caretakers").select("*").limit(1).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception:
            pass

    # Fall back to _SEEDED_STAFF caretaker entry
    seeded = next(
        (s for s in _SEEDED_STAFF.values() if s.get("role") == "caretaker"),
        None
    )
    if seeded:
        return {
            "id": seeded["id"],
            "name": seeded["full_name"],
            "email": seeded["email"],
            "password_hash": seeded["password_hash"],
            "contact": seeded.get("phone_number", ""),
        }
    return None


# ── GET /landlord/status ──────────────────────────────────────────────────────

@router.get("/status")
def landlord_status():
    """Check if a landlord account exists (used by UI to decide whether to show bootstrap signup)."""
    db = get_supabase_client()
    landlord = _get_active_landlord(db)
    return {
        "has_landlord": landlord is not None,
        "email": landlord.get("email") if landlord else None,
        "name": landlord.get("name") if landlord else None,
    }


# ── POST /landlord/signup ─────────────────────────────────────────────────────

@router.post("/signup")
def landlord_signup(req: LandlordSignupRequest):
    """
    One-time bootstrap signup for the primary landlord.
    Only allowed if NO landlord row exists yet (returns 409 if one already exists).
    """
    db = get_supabase_client()

    # Check without auto-bootstrap (raw check)
    existing = None
    if hasattr(db, "landlords"):
        existing = db.landlords[0] if db.landlords else None
    else:
        try:
            res = db.table("landlords").select("*").limit(1).execute()
            if res.data:
                existing = res.data[0]
        except Exception:
            pass

    if existing:
        raise HTTPException(
            status_code=409,
            detail="A landlord account already exists. Use the Dashboard to update credentials.",
        )

    user_id = str(uuid.uuid4())
    pw_hash = hash_password(req.password)
    now_iso = datetime.now(timezone.utc).isoformat()

    new_landlord = {
        "id": user_id,
        "name": req.name.strip(),
        "email": req.email.strip().lower(),
        "password_hash": pw_hash,
        "contact": str(req.contact or "").strip(),
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    if hasattr(db, "landlords"):
        db.landlords.append(new_landlord)
    else:
        try:
            db.table("landlords").insert(new_landlord).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to create landlord account: {str(e)}")

    profile = {
        "id": user_id,
        "full_name": req.name.strip(),
        "email": req.email.strip().lower(),
        "role": "landlord",
        "phone_number": req.contact or "",
    }
    token = create_jwt(profile)

    return {
        "status": "success",
        "message": "Landlord account created successfully.",
        "user": profile,
        "token": token,
    }


# ── POST /landlord/update ─────────────────────────────────────────────────────

@router.post("/update")
def landlord_direct_update(
    req: LandlordDirectUpdateRequest,
    current_user: dict = Depends(require_role(STAFF_ROLES)),
):
    """
    Direct credential update for the landlord.
    Requires the current password for verification — no email confirmation needed.
    Applies changes immediately.
    """
    db = get_supabase_client()
    landlord = _get_active_landlord(db)

    if not landlord:
        raise HTTPException(status_code=404, detail="No active landlord account found.")

    # Verify current password
    if not verify_password(req.current_password, landlord.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    # Build updates
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if req.new_name and req.new_name.strip():
        updates["name"] = req.new_name.strip()
    if req.new_email and req.new_email.strip():
        updates["email"] = req.new_email.strip().lower()
    if req.new_password and req.new_password.strip():
        if len(req.new_password) < 8:
            raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
        updates["password_hash"] = hash_password(req.new_password)
    if req.new_contact and req.new_contact.strip():
        updates["contact"] = req.new_contact.strip()

    if len(updates) <= 1:
        raise HTTPException(status_code=400, detail="No changes provided. Fill in at least one field.")

    # Sync _SEEDED_STAFF so runtime logins pick up the change immediately
    for k in list(_SEEDED_STAFF.keys()):
        if _SEEDED_STAFF[k].get("role") == "landlord":
            entry = _SEEDED_STAFF.pop(k)
            entry["full_name"] = updates.get("name", entry["full_name"])
            entry["email"] = updates.get("email", entry["email"])
            entry["password_hash"] = updates.get("password_hash", entry["password_hash"])
            entry["phone_number"] = updates.get("contact", entry.get("phone_number", ""))
            _SEEDED_STAFF[entry["email"]] = entry
            break

    # Apply to DB/mock if table exists
    if hasattr(db, "landlords"):
        landlord.update(updates)
    else:
        try:
            # Check if row exists first before update to avoid schema errors if missing
            res = db.table("landlords").select("id").eq("id", landlord.get("id")).execute()
            if res.data:
                db.table("landlords").update(updates).eq("id", landlord.get("id")).execute()
            else:
                landlord_rec = {
                    "id": landlord.get("id"),
                    "name": updates.get("name", landlord.get("name", "")),
                    "email": updates.get("email", landlord.get("email", "")),
                    "password_hash": updates.get("password_hash", landlord.get("password_hash", "")),
                    "contact": updates.get("contact", landlord.get("contact", "")),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                db.table("landlords").insert(landlord_rec).execute()
        except Exception as e:
            print(f"[Supabase Landlord Update Warning]: {e}")

    applied = [k.replace("_hash", "").replace("_", " ") for k in updates if k != "updated_at"]
    return {
        "status": "success",
        "message": f"Landlord account updated successfully. Changed: {', '.join(applied)}. Please log in again with your new credentials.",
    }


# ── POST /landlord/update-caretaker ──────────────────────────────────────────

@router.post("/update-caretaker")
def update_caretaker(
    req: CaretakerUpdateRequest,
    current_user: dict = Depends(require_role(LANDLORD_ONLY)),
):
    """
    Landlord-only: update the caretaker's login credentials (name, email, password).
    Changes are applied immediately to the caretakers table and _SEEDED_STAFF in-memory.
    """
    db = get_supabase_client()

    if not req.new_name and not req.new_email and not req.new_password:
        raise HTTPException(status_code=400, detail="No changes provided. Fill in at least one field.")

    if req.new_password and len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")

    now_iso = datetime.now(timezone.utc).isoformat()
    caretaker = _get_active_caretaker(db)

    updates = {"updated_at": now_iso}
    if req.new_name and req.new_name.strip():
        updates["name"] = req.new_name.strip()
    if req.new_email and req.new_email.strip():
        updates["email"] = req.new_email.strip().lower()
    if req.new_password and req.new_password.strip():
        updates["password_hash"] = hash_password(req.new_password)

    # Sync _SEEDED_STAFF (so runtime login picks it up immediately)
    for k in list(_SEEDED_STAFF.keys()):
        if _SEEDED_STAFF[k].get("role") == "caretaker":
            entry = _SEEDED_STAFF.pop(k)
            entry["full_name"] = updates.get("name", entry["full_name"])
            entry["email"] = updates.get("email", entry["email"])
            entry["password_hash"] = updates.get("password_hash", entry["password_hash"])
            _SEEDED_STAFF[entry["email"]] = entry
            break

    # Persist to DB/mock
    if hasattr(db, "caretakers"):
        if caretaker and db.caretakers:
            # Update in-place
            for idx, c in enumerate(db.caretakers):
                if c.get("id") == caretaker.get("id"):
                    db.caretakers[idx].update(updates)
                    break
        else:
            # Bootstrap caretaker into mock
            new_record = {
                "id": caretaker.get("id", str(uuid.uuid4())) if caretaker else str(uuid.uuid4()),
                "name": updates.get("name", caretaker.get("name", "Caretaker Admin") if caretaker else "Caretaker Admin"),
                "email": updates.get("email", caretaker.get("email", "") if caretaker else ""),
                "password_hash": updates.get("password_hash", caretaker.get("password_hash", "") if caretaker else ""),
                "contact": "",
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            db.caretakers.append(new_record)
    else:
        try:
            if caretaker:
                existing_in_db = db.table("caretakers").select("id").eq("id", caretaker.get("id")).execute()
                if existing_in_db.data:
                    db.table("caretakers").update(updates).eq("id", caretaker.get("id")).execute()
                else:
                    new_record = {
                        "id": caretaker.get("id", str(uuid.uuid4())),
                        "name": updates.get("name", caretaker.get("name", "Caretaker Admin")),
                        "email": updates.get("email", caretaker.get("email", "")),
                        "password_hash": updates.get("password_hash", caretaker.get("password_hash", "")),
                        "contact": "",
                        "created_at": now_iso,
                        "updated_at": now_iso,
                    }
                    db.table("caretakers").insert(new_record).execute()
        except Exception as e:
            # Table may not exist in Supabase — just log and continue (in-memory sync already done)
            print(f"[Caretaker DB Update Warning]: {e}")

    applied = [k.replace("_hash", "").replace("_", " ") for k in updates if k != "updated_at"]
    return {
        "status": "success",
        "message": f"Caretaker account updated successfully. Changed: {', '.join(applied)}. Caretaker should log in with new credentials.",
    }


# ── POST /landlord/forgot-password ───────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(req: LandlordForgotPasswordRequest):
    """
    Generates a password reset token for matching Landlord, Caretaker, or Tenant account and dispatches email via Resend directly to registered email.
    Always returns generic success to avoid account enumeration.
    """
    email_clean = req.email.strip().lower()
    generic_response = {
        "status": "success",
        "message": "If the email matches an active account, password reset instructions have been sent to your registered email.",
    }

    db = get_supabase_client()
    target_account = None
    account_role = None

    # Check landlord account
    landlord = _get_active_landlord(db)
    if landlord and landlord.get("email", "").lower() == email_clean:
        target_account = landlord
        account_role = "landlord"

    # Check caretaker account
    if not target_account:
        caretaker = _get_active_caretaker(db)
        if caretaker and caretaker.get("email", "").lower() == email_clean:
            target_account = caretaker
            account_role = "caretaker"

    # Check tenant account
    if not target_account:
        if hasattr(db, "tenants"):
            tenant = next((t for t in db.tenants if t.get("email", "").lower() == email_clean), None)
            if tenant:
                target_account = tenant
                account_role = "tenant"
        else:
            try:
                res_t = db.table("tenants").select("*").eq("email", email_clean).execute()
                if res_t.data:
                    target_account = res_t.data[0]
                    account_role = "tenant"
            except Exception:
                pass

    # Check seeded staff accounts
    if not target_account:
        if email_clean in _SEEDED_STAFF:
            target_account = _SEEDED_STAFF[email_clean]
            account_role = target_account.get("role", "landlord")

    if not target_account:
        return generic_response

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    reset_row = {
        "id": str(uuid.uuid4()),
        "landlord_id": target_account.get("id"),
        "role": account_role,
        "token": token,
        "expires_at": expires_at.isoformat(),
        "used": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if hasattr(db, "password_resets"):
        db.password_resets.append(reset_row)
    else:
        try:
            db.table("password_resets").insert(reset_row).execute()
        except Exception as e:
            print(f"[Password Reset Insert Warning]: {e}")

    base_url = os.getenv("FRONTEND_URL") or os.getenv("APP_URL") or "https://apartment-management-lime.vercel.app"
    reset_url = f"{base_url}/reset-password.html?token={token}"
    send_landlord_password_reset_email(email_clean, reset_url)

    return generic_response


# ── POST /landlord/reset-password ────────────────────────────────────────────

@router.post("/reset-password")
def reset_password(req: LandlordResetPasswordRequest):
    """Validates reset token, updates password_hash on the landlord, caretaker, or tenant row, marks token used."""
    if not req.token:
        raise HTTPException(status_code=400, detail="Missing reset token.")

    db = get_supabase_client()
    now_utc = datetime.now(timezone.utc)

    reset_row = None
    if hasattr(db, "password_resets"):
        reset_row = next((r for r in db.password_resets if r.get("token") == req.token), None)
    else:
        try:
            res = db.table("password_resets").select("*").eq("token", req.token).execute()
            if res.data:
                reset_row = res.data[0]
        except Exception:
            pass

    if not reset_row:
        raise HTTPException(status_code=404, detail="Invalid or non-existent password reset token.")
    if reset_row.get("used"):
        raise HTTPException(status_code=400, detail="This password reset link has already been used.")

    exp_str = reset_row.get("expires_at")
    exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00")) if exp_str else now_utc
    if now_utc > exp_dt:
        raise HTTPException(status_code=400, detail="This password reset link has expired. Please request a new one.")

    pw_hash = hash_password(req.new_password)
    account_id = reset_row.get("landlord_id")
    role = reset_row.get("role", "landlord")

    # Sync _SEEDED_STAFF if matching
    for email_k, staff in list(_SEEDED_STAFF.items()):
        if staff.get("id") == account_id or staff.get("role") == role:
            staff["password_hash"] = pw_hash

    if role == "tenant":
        if hasattr(db, "tenants"):
            tenant = next((t for t in db.tenants if t.get("id") == account_id), None)
            if tenant:
                tenant["password"] = req.new_password
                tenant["password_hash"] = pw_hash
            reset_row["used"] = True
        else:
            try:
                db.table("tenants").update({"password_hash": pw_hash}).eq("id", account_id).execute()
                db.table("password_resets").update({"used": True}).eq("id", reset_row.get("id")).execute()
            except Exception as e:
                print(f"[Tenant Reset Update Warning]: {e}")
                reset_row["used"] = True
    elif role == "caretaker":
        if hasattr(db, "caretakers"):
            caretaker = next((c for c in db.caretakers if c.get("id") == account_id), None)
            if caretaker:
                caretaker["password_hash"] = pw_hash
                caretaker["updated_at"] = now_utc.isoformat()
            reset_row["used"] = True
        else:
            try:
                db.table("caretakers").update({"password_hash": pw_hash, "updated_at": now_utc.isoformat()}).eq("id", account_id).execute()
                db.table("password_resets").update({"used": True}).eq("id", reset_row.get("id")).execute()
            except Exception as e:
                print(f"[Caretaker Reset Update Warning]: {e}")
                reset_row["used"] = True
    else:
        if hasattr(db, "landlords"):
            landlord = next((l for l in db.landlords if l.get("id") == account_id), None)
            if landlord:
                landlord["password_hash"] = pw_hash
                landlord["updated_at"] = now_utc.isoformat()
            reset_row["used"] = True
        else:
            try:
                db.table("landlords").update({"password_hash": pw_hash, "updated_at": now_utc.isoformat()}).eq("id", account_id).execute()
                db.table("password_resets").update({"used": True}).eq("id", reset_row.get("id")).execute()
            except Exception as e:
                print(f"[Landlord Reset Update Warning]: {e}")
                reset_row["used"] = True

    return {"status": "success", "message": "Password reset successful! You may now sign in with your new password."}


# ── POST /landlord/request-change (Legacy email-confirmation flow) ─────────────

@router.post("/request-change")
def request_landlord_change(
    req: LandlordChangeRequest,
    current_user: dict = Depends(require_role(STAFF_ROLES)),
):
    """
    Legacy email-confirmation flow (kept for backward compatibility).
    Prefer POST /landlord/update for direct credential changes.
    """
    db = get_supabase_client()
    landlord = _get_active_landlord(db)
    if not landlord:
        raise HTTPException(status_code=404, detail="No active landlord account found.")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    now_iso = datetime.now(timezone.utc).isoformat()

    pw_hash = hash_password(req.new_password) if req.new_password else None

    pending_entry = {
        "id": str(uuid.uuid4()),
        "requested_by": landlord.get("id"),
        "new_name": req.new_name.strip() if req.new_name else None,
        "new_email": req.new_email.strip().lower() if req.new_email else None,
        "new_password_hash": pw_hash,
        "new_contact": req.new_contact.strip() if req.new_contact else None,
        "token": token,
        "expires_at": expires_at.isoformat(),
        "status": "pending",
        "created_at": now_iso,
    }

    if hasattr(db, "pending_landlord_changes"):
        db.pending_landlord_changes.append(pending_entry)
    else:
        try:
            db.table("pending_landlord_changes").insert(pending_entry).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to record pending change: {str(e)}")

    base_url = os.getenv("FRONTEND_URL") or os.getenv("APP_URL") or "https://apartment-management-lime.vercel.app"
    confirm_url = f"{base_url}/api/landlord/confirm-change?token={token}"
    current_email = landlord.get("email")
    send_landlord_change_confirmation_email(
        current_email=current_email,
        new_name=req.new_name or landlord.get("name"),
        new_email=req.new_email or landlord.get("email"),
        confirm_url=confirm_url,
    )

    return {
        "status": "success",
        "message": f"Change request initiated! A confirmation email has been sent to {current_email}. Changes take effect once confirmed.",
    }


# ── GET /landlord/confirm-change (Legacy) ────────────────────────────────────

@router.get("/confirm-change")
def confirm_landlord_change(token: str):
    """Validates email token and applies pending landlord changes."""
    if not token:
        raise HTTPException(status_code=400, detail="Missing confirmation token.")

    db = get_supabase_client()
    now_utc = datetime.now(timezone.utc)

    pending_row = None
    if hasattr(db, "pending_landlord_changes"):
        pending_row = next((p for p in db.pending_landlord_changes if p.get("token") == token), None)
    else:
        try:
            res = db.table("pending_landlord_changes").select("*").eq("token", token).execute()
            if res.data:
                pending_row = res.data[0]
        except Exception:
            pass

    if not pending_row:
        raise HTTPException(status_code=404, detail="Invalid or non-existent confirmation token.")
    if pending_row.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"This link has already been {pending_row.get('status')}.")

    exp_str = pending_row.get("expires_at")
    exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00")) if exp_str else now_utc
    if now_utc > exp_dt:
        raise HTTPException(status_code=400, detail="Confirmation link expired (valid 30 min). Submit a new change request.")

    landlord = _get_active_landlord(db)
    if not landlord:
        raise HTTPException(status_code=404, detail="Active landlord profile not found.")

    updates = {}
    if pending_row.get("new_name"):
        updates["name"] = pending_row["new_name"]
    if pending_row.get("new_email"):
        updates["email"] = pending_row["new_email"]
    if pending_row.get("new_password_hash"):
        updates["password_hash"] = pending_row["new_password_hash"]
    if pending_row.get("new_contact"):
        updates["contact"] = pending_row["new_contact"]
    updates["updated_at"] = now_utc.isoformat()

    if hasattr(db, "landlords"):
        landlord.update(updates)
        pending_row["status"] = "confirmed"
    else:
        try:
            db.table("landlords").update(updates).eq("id", landlord.get("id")).execute()
            db.table("pending_landlord_changes").update({"status": "confirmed"}).eq("id", pending_row.get("id")).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to apply update: {str(e)}")

    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Account Updated</title>
    <style>body{font-family:serif;background:#fbf9f4;color:#1c1a17;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}</style>
    </head>
    <body>
      <div style="background:#ffffff;padding:40px;border-radius:16px;border:1px solid #dfd9cd;max-width:450px;text-align:center;box-shadow:0 10px 25px rgba(0,0,0,0.05);">
        <div style="font-size:48px;margin-bottom:16px;">✅</div>
        <h2 style="font-weight:300;margin-bottom:12px;">Landlord Account Updated</h2>
        <p style="font-size:14px;color:#666;line-height:1.6;margin-bottom:24px;">Your credentials have been updated successfully.</p>
        <a href="/index.html" style="display:inline-block;background:#c2593f;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-size:13px;font-weight:600;">Return to Login &rarr;</a>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
