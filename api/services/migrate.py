"""
Auto-migration service.
Runs safe ALTER TABLE statements on every startup to ensure the live
Supabase schema matches what the application expects.
All statements use IF NOT EXISTS / try-except so they are idempotent.
"""
import os
import logging

logger = logging.getLogger(__name__)

MIGRATIONS = [
    # Make landlord_id on buildings optional (we may not have auth.users)
    "ALTER TABLE buildings ALTER COLUMN landlord_id DROP NOT NULL",
    # Make unit assignment optional on tenants (assigned after approval)
    "ALTER TABLE tenants ALTER COLUMN unit_id DROP NOT NULL",
    # Make lease_start_date optional on tenants
    "ALTER TABLE tenants ALTER COLUMN lease_start_date DROP NOT NULL",
    # Add password column if it doesn't exist
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS password TEXT",
    # Add is_approved column with default true for backwards compat
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT FALSE",
    # Make building_id on units optional so partial inserts don't fail
    "ALTER TABLE units ALTER COLUMN building_id DROP NOT NULL",
]


def run_migrations():
    """Run all schema migrations against the live Supabase database."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    
    # Only run if real credentials are present
    if not url or not key or "your-project" in url:
        logger.info("[Migrate] Skipping migrations — no real Supabase credentials found.")
        return

    try:
        from supabase import create_client
        client = create_client(url, key)
        
        for sql in MIGRATIONS:
            try:
                client.rpc("exec_sql", {"query": sql}).execute()
                logger.info(f"[Migrate] OK: {sql[:60]}…")
            except Exception as e:
                # Many of these will "fail" if the column already doesn't have NOT NULL
                # That's fine — log and move on
                logger.warning(f"[Migrate] Skipped (may already be applied): {str(e)[:80]}")
    except Exception as e:
        logger.error(f"[Migrate] Migration runner failed: {e}")
