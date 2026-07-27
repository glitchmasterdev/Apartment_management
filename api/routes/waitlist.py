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

    # Optionally send notification email via Resend (non-blocking)
    try:
        import resend, os
        resend.api_key = os.getenv("RESEND_API_KEY", "")
        if resend.api_key:
            resend.Emails.send({
                "from": "Nairobi Rentals <noreply@nairobirentals.com>",
                "to": ["billionare081@gmail.com"],
                "subject": f"🏢 New Early Access Request — {req.full_name}",
                "html": f"""
                <h2>New Early Access Signup</h2>
                <table style="border-collapse:collapse;width:100%;font-family:sans-serif;font-size:14px;">
                  <tr><td style="padding:6px 12px;font-weight:bold;background:#f5f5f5;">Name</td><td style="padding:6px 12px;">{req.full_name}</td></tr>
                  <tr><td style="padding:6px 12px;font-weight:bold;background:#f5f5f5;">Email</td><td style="padding:6px 12px;">{req.email}</td></tr>
                  <tr><td style="padding:6px 12px;font-weight:bold;background:#f5f5f5;">Phone</td><td style="padding:6px 12px;">{req.phone_number or '—'}</td></tr>
                  <tr><td style="padding:6px 12px;font-weight:bold;background:#f5f5f5;">No. of Units</td><td style="padding:6px 12px;">{req.num_units or '—'}</td></tr>
                  <tr><td style="padding:6px 12px;font-weight:bold;background:#f5f5f5;">Location(s)</td><td style="padding:6px 12px;">{req.locations or '—'}</td></tr>
                  <tr><td style="padding:6px 12px;font-weight:bold;background:#f5f5f5;">Current Method</td><td style="padding:6px 12px;">{req.current_method or '—'}</td></tr>
                </table>
                """,
            })
    except Exception:
        pass

    return {"status": "success", "message": "You're on the list! We'll be in touch within 48 hours."}
