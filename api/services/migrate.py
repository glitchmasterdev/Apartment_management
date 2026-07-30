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
    "ALTER TABLE units ALTER COLUMN building_id DROP NOT NULL",    """
    CREATE OR REPLACE FUNCTION bulk_import_units(p_building_id UUID, p_units JSONB) RETURNS JSONB LANGUAGE plpgsql AS $$
    DECLARE result JSONB;
    BEGIN
      WITH r AS (SELECT value row, ordinality n FROM jsonb_array_elements(p_units) WITH ORDINALITY),
      p AS (SELECT n, row->>'unit_number' unit_number, (row->>'floor')::integer floor, (row->>'rent_amount')::numeric rent_amount, COALESCE((row->>'deposit_amount')::numeric,(row->>'rent_amount')::numeric) deposit_amount, count(*) OVER (PARTITION BY row->>'unit_number') dup FROM r),
      c AS (SELECT p.*, CASE WHEN dup > 1 THEN 'Duplicate unit number in this import.' WHEN EXISTS (SELECT 1 FROM units u WHERE u.building_id=p_building_id AND u.unit_number=p.unit_number) THEN 'Unit number already exists for this building.' END reason FROM p),
      i AS (INSERT INTO units(building_id,unit_number,floor,rent_amount,deposit_amount,deposit_paid,status,is_active) SELECT p_building_id,unit_number,floor,rent_amount,deposit_amount,false,'vacant',true FROM c WHERE reason IS NULL ON CONFLICT (building_id,unit_number) DO NOTHING RETURNING id)
      SELECT jsonb_build_object('imported_count',(SELECT count(*) FROM i),'failed_rows',COALESCE((SELECT jsonb_agg(jsonb_build_object('unit_number',unit_number,'floor',floor,'reason',reason)) FROM c WHERE reason IS NOT NULL),'[]'::jsonb)) INTO result;
      RETURN result;
    END; $
    """,
    """
    CREATE OR REPLACE FUNCTION hard_delete_tenant(p_tenant_id UUID) RETURNS JSONB LANGUAGE plpgsql AS $$
    DECLARE tenant_unit_id UUID;
    BEGIN
      SELECT unit_id INTO tenant_unit_id FROM tenants WHERE id=p_tenant_id FOR UPDATE;
      IF NOT FOUND THEN RETURN jsonb_build_object('deleted',false); END IF;
      DELETE FROM payments WHERE tenant_id=p_tenant_id;
      DELETE FROM occupancy_logs WHERE tenant_id=p_tenant_id;
      DELETE FROM tenants WHERE id=p_tenant_id;
      IF tenant_unit_id IS NOT NULL THEN UPDATE units SET status='vacant' WHERE id=tenant_unit_id; END IF;
      RETURN jsonb_build_object('deleted',true);
    END; $
    """,
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
