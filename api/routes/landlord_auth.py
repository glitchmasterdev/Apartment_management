"""
landlord_auth.py — Dynamic Landlord Account Management Routes.

Endpoints:
  GET  /api/landlord/status — Returns whether a landlord row exists (has_landlord: bool)
  POST /api/landlord/signup — Bootstrap signup (allowed only if no landlord exists, else 409)
  POST /api/landlord/request-change — Request landlord changes (authenticated staff only), sends token link to current email
  GET  /api/landlord/confirm-change — Validates token, applies pending change to landlords row
  POST /api/landlord/forgot-password — Generic success, sends password reset token link to landlord email
  POST /api/landlord/reset-password — Validates reset token and sets new password_hash
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
    LandlordForgotPasswordRequest,
    LandlordResetPasswordRequest,
)
from api.services.supabase_client import get_supabase_client
from api.services.auth_middleware import require_role, get_current_user
from api.services.email import (
    send_landlord_change_confirmation_email,
    send_landlord_password_reset_email,
)
from api.routes.auth import hash_password, create_jwt

router = APIRouter(prefix="/landlord", tags=["Landlord Management"])

STAFF = ["landlord", "caretaker"]


def _get_active_landlord(db):
    """Fetches the primary active landlord row from Supabase or Mock client."""
    if hasattr(db, "landlords"):
        if db.landlords:
            return db.landlords[0]
        return None
    try:
        res = db.table("landlords").select("*").limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass
    return None


@router.get("/status")
def landlord_status():
    """Check if a landlord account exists (used by UI to render bootstrap signup or standard staff portal)."""
    db = get_supabase_client()
    landlord = _get_active_landlord(db)
    return {
        "has_landlord": landlord is not None,
        "email": landlord.get("email") if landlord else None,
        "name": landlord.get("name") if landlord else None,
    }


@router.post("/signup")
def landlord_signup(req: LandlordSignupRequest):
    """
    One-time bootstrap signup for the primary landlord.
    Only allowed if NO landlord row exists yet. Returns 409 Conflict if a landlord already exists.
    """
    db = get_supabase_client()
    existing = _get_active_landlord(db)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="A landlord account already exists. Use Staff Portal login or forgot password.",
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


@router.post("/request-change")
def request_landlord_change(
    req: LandlordChangeRequest,
    current_user: dict = Depends(require_role(STAFF)),
):
    """
    Staff submits requested new landlord details.
    Does NOT update the live landlords row immediately.
    Creates a pending_landlord_changes row with a 30-minute token and emails confirmation
    to the CURRENT landlord's email.
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

    # Send confirmation link to CURRENT landlord's email
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
        "message": f"Change request initiated! A confirmation email has been sent to current email: {current_email}. Changes will take effect once confirmed.",
    }


@router.get("/confirm-change")
def confirm_landlord_change(token: str):
    """
    Validates token, applies pending change to the live landlords row,
    marks pending row as confirmed, logs the change, and returns clear confirmation response.
    """
    if not token:
        raise HTTPException(status_code=400, detail="Missing confirmation token.")

    db = get_supabase_client()
    now_utc = datetime.now(timezone.utc)

    # Fetch pending change record
    pending_row = None
    if hasattr(db, "pending_landlord_changes"):
        pending_row = next((p for p in db.pending_landlord_changes if p.get("token") == token), None)
    else:
        try:
            res = db.table("pending_landlord_changes").select("*").eq("token", token).execute()
            if res.data and len(res.data) > 0:
                pending_row = res.data[0]
        except Exception:
            pass

    if not pending_row:
        raise HTTPException(status_code=404, detail="Invalid or non-existent confirmation token.")

    if pending_row.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"This confirmation link has already been {pending_row.get('status')}.")

    # Expiry check
    exp_str = pending_row.get("expires_at")
    exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00")) if exp_str else now_utc
    if now_utc > exp_dt:
        if hasattr(db, "pending_landlord_changes"):
            pending_row["status"] = "expired"
        else:
            try:
                db.table("pending_landlord_changes").update({"status": "expired"}).eq("id", pending_row.get("id")).execute()
            except Exception:
                pass
        raise HTTPException(status_code=400, detail="This confirmation link has expired (valid for 30 minutes). Please submit a new change request.")

    # Get live landlord record
    landlord = _get_active_landlord(db)
    if not landlord:
        raise HTTPException(status_code=404, detail="Active landlord profile not found.")

    old_email = landlord.get("email")

    # Build updates dict
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

    # Update live landlord record
    if hasattr(db, "landlords"):
        landlord.update(updates)
        pending_row["status"] = "confirmed"
        db.landlord_change_log.append({
            "id": str(uuid.uuid4()),
            "landlord_id": landlord.get("id"),
            "old_email": old_email,
            "new_email": landlord.get("email"),
            "changed_by": "token_confirmation",
            "changed_at": now_utc.isoformat(),
        })
    else:
        try:
            db.table("landlords").update(updates).eq("id", landlord.get("id")).execute()
            db.table("pending_landlord_changes").update({"status": "confirmed"}).eq("id", pending_row.get("id")).execute()
            db.table("landlord_change_log").insert({
                "id": str(uuid.uuid4()),
                "landlord_id": landlord.get("id"),
                "old_email": old_email,
                "new_email": updates.get("email", old_email),
                "changed_by": "token_confirmation",
                "changed_at": now_utc.isoformat(),
            }).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to apply landlord update: {str(e)}")

    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Landlord Profile Updated</title>
    <style>body{font-family:serif;background:#fbf9f4;color:#1c1a17;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}</style>
    </head>
    <body>
      <div style="background:#ffffff;padding:40px;border-radius:16px;border:1px solid #dfd9cd;max-width:450px;text-align:center;box-shadow:0 10px 25px rgba(0,0,0,0.05);">
        <div style="font-size:48px;margin-bottom:16px;">✅</div>
        <h2 style="font-weight:300;margin-bottom:12px;">Landlord Account Updated</h2>
        <p style="font-size:14px;color:#666;line-height:1.6;margin-bottom:24px;">Your landlord account profile and credentials have been successfully updated.</p>
        <a href="/index.html" style="display:inline-block;background:#c2593f;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-size:13px;font-weight:600;">Return to Staff Login &rarr;</a>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.post("/forgot-password")
def forgot_password(req: LandlordForgotPasswordRequest):
    """
    Generates a password reset token for matching landlord email and dispatches email via Resend.
    Always returns generic success message regardless of email match to avoid account enumeration.
    """
    email_clean = req.email.strip().lower()
    generic_response = {
        "status": "success",
        "message": "If the email matches an active landlord account, password reset instructions have been sent.",
    }

    db = get_supabase_client()
    landlord = None
    if hasattr(db, "landlords"):
        landlord = next((l for l in db.landlords if l.get("email") == email_clean), None)
    else:
        try:
            res = db.table("landlords").select("*").eq("email", email_clean).execute()
            if res.data and len(res.data) > 0:
                landlord = res.data[0]
        except Exception:
            pass

    if landlord:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        reset_row = {
            "id": str(uuid.uuid4()),
            "landlord_id": landlord.get("id"),
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


@router.post("/reset-password")
def reset_password(req: LandlordResetPasswordRequest):
    """Validates reset token, updates password_hash on the landlord row, and marks token as used."""
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
            if res.data and len(res.data) > 0:
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
    landlord_id = reset_row.get("landlord_id")

    if hasattr(db, "landlords"):
        landlord = next((l for l in db.landlords if l.get("id") == landlord_id), None)
        if landlord:
            landlord["password_hash"] = pw_hash
            landlord["updated_at"] = now_utc.isoformat()
        reset_row["used"] = True
    else:
        try:
            db.table("landlords").update({"password_hash": pw_hash, "updated_at": now_utc.isoformat()}).eq("id", landlord_id).execute()
            db.table("password_resets").update({"used": True}).eq("id", reset_row.get("id")).execute()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to reset password: {str(e)}")

    return {"status": "success", "message": "Password reset successful! You may now sign in with your new password."}
