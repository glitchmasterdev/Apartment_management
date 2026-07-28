"""
waitlist.py — Public endpoint to capture Early Access / waitlist signups from the landing page.
No authentication required. Saves entry to Supabase 'waitlist' table.
"""
from fastapi import APIRouter, HTTPException
from api.models import WaitlistEntry
from api.services.supabase_client import get_supabase_client
import uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/waitlist", tags=["Waitlist"])


@router.post("")
def join_waitlist(req: WaitlistEntry):
    """Save an early-access enquiry to the waitlist table."""
    db = get_supabase_client()

    entry = {
        "id": str(uuid.uuid4()),
        "full_name": str(req.full_name).strip()[:200],
        "email": str(req.email).strip().lower()[:200],
        "phone_number": str(req.phone_number or "").strip()[:50],
        "num_units": str(req.num_units or "").strip()[:100],
        "locations": str(req.locations or "").strip()[:300],
        "current_method": str(req.current_method or "").strip()[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if hasattr(db, "waitlist"):
        # In-memory mock mode
        if not hasattr(db, "_waitlist_entries"):
            db._waitlist_entries = []
        db._waitlist_entries.append(entry)
    else:
        try:
            db.table("waitlist").insert(entry).execute()
        except Exception as e:
            # Table might not exist yet — still return success so user isn't blocked
            print(f"[Waitlist] DB insert failed (table may not exist yet): {e}")

    # Send notification email via core send_email service to sammyroland90@gmail.com
    try:
        from api.services.email import send_email
        notify_body = f"""
        <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #ffffff; padding: 24px; border-radius: 12px; border: 1px solid #c2593f;">
          <h2 style="color: #c2593f; margin-top: 0;">🏢 New Early Access Signup</h2>
          <p style="color: #475569; font-size: 14px;">A new prospective landlord has requested early access from the landing page:</p>
          <table style="border-collapse: collapse; width: 100%; font-size: 14px; margin: 16px 0;">
            <tr><td style="padding: 8px 12px; font-weight: bold; background: #f8fafc; border: 1px solid #e2e8f0;">Full Name</td><td style="padding: 8px 12px; border: 1px solid #e2e8f0;">{req.full_name}</td></tr>
            <tr><td style="padding: 8px 12px; font-weight: bold; background: #f8fafc; border: 1px solid #e2e8f0;">Email Address</td><td style="padding: 8px 12px; border: 1px solid #e2e8f0;"><a href="mailto:{req.email}">{req.email}</a></td></tr>
            <tr><td style="padding: 8px 12px; font-weight: bold; background: #f8fafc; border: 1px solid #e2e8f0;">Phone Number</td><td style="padding: 8px 12px; border: 1px solid #e2e8f0;">{req.phone_number or '—'}</td></tr>
            <tr><td style="padding: 8px 12px; font-weight: bold; background: #f8fafc; border: 1px solid #e2e8f0;">No. of Units</td><td style="padding: 8px 12px; border: 1px solid #e2e8f0;">{req.num_units or '—'}</td></tr>
            <tr><td style="padding: 8px 12px; font-weight: bold; background: #f8fafc; border: 1px solid #e2e8f0;">Location(s)</td><td style="padding: 8px 12px; border: 1px solid #e2e8f0;">{req.locations or '—'}</td></tr>
            <tr><td style="padding: 8px 12px; font-weight: bold; background: #f8fafc; border: 1px solid #e2e8f0;">Current Collection Method</td><td style="padding: 8px 12px; border: 1px solid #e2e8f0;">{req.current_method or '—'}</td></tr>
          </table>
          <p style="color: #64748b; font-size: 12px; margin-bottom: 0;">Nairobi Rentals • Early Access Notification System</p>
        </div>
        """
        send_email("sammyroland90@gmail.com", f"🏢 New Early Access Request — {req.full_name}", notify_body)
    except Exception as e:
        print(f"[Waitlist Email Warning]: {e}")

    return {"status": "success", "message": "You're on the list! We'll be in touch within 48 hours."}
