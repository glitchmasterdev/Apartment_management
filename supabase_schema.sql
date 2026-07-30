-- ====================================================================
-- NAIROBI RENTAL MANAGEMENT PLATFORM - SUPABASE SQL SCHEMA
-- ====================================================================

-- 1. PROFILES (Extends auth.users)
CREATE TABLE IF NOT EXISTS profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('landlord', 'caretaker')),
  landlord_id UUID REFERENCES profiles(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. PAYMENT CONFIGURATIONS
CREATE TABLE IF NOT EXISTS payment_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  landlord_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE UNIQUE,
  paybill_number TEXT NOT NULL,
  account_reference_format TEXT DEFAULT 'LND-{id}-{building}-{unit}'
);

-- 3. BUILDINGS
CREATE TABLE IF NOT EXISTS buildings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  landlord_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  location TEXT,
  total_floors INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. UNITS
CREATE TABLE IF NOT EXISTS units (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  unit_number TEXT NOT NULL,
  floor INTEGER DEFAULT 1,
  rent_amount NUMERIC(10,2) NOT NULL,
  deposit_amount NUMERIC(10,2) DEFAULT 0,
  deposit_paid BOOLEAN DEFAULT FALSE,
  status TEXT DEFAULT 'vacant' CHECK (status IN ('occupied', 'vacant', 'maintenance')),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(building_id, unit_number)
);

-- 5. TENANTS
CREATE TABLE IF NOT EXISTS tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  unit_id UUID REFERENCES units(id) ON DELETE SET NULL,
  full_name TEXT NOT NULL,
  phone_number TEXT NOT NULL,
  email TEXT UNIQUE,
  password_hash TEXT,
  account_number TEXT UNIQUE,
  lease_start_date DATE,
  monthly_rent NUMERIC(10,2) DEFAULT 0,
  is_active BOOLEAN DEFAULT FALSE,
  is_approved BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. PAYMENTS
CREATE TABLE IF NOT EXISTS payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
  amount_paid NUMERIC(10,2) NOT NULL,
  payment_date TIMESTAMPTZ DEFAULT NOW(),
  mpesa_code TEXT,
  tenant_message TEXT,
  receipt_url TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  approved_by UUID REFERENCES profiles(id),
  approved_at TIMESTAMPTZ,
  rejection_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. OCCUPANCY LOGS
CREATE TABLE IF NOT EXISTS occupancy_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
  tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
  action_type TEXT NOT NULL CHECK (action_type IN ('MOVE_IN', 'MOVE_OUT', 'DAILY_PRESENT', 'DAILY_ABSENT')),
  timestamp TIMESTAMPTZ DEFAULT NOW(),
  performed_by UUID NOT NULL REFERENCES profiles(id),
  notes TEXT
);

-- 8. EXPENSES
CREATE TABLE IF NOT EXISTS expenses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  category TEXT NOT NULL CHECK (category IN ('security', 'water', 'electricity', 'garbage', 'repairs', 'salaries', 'other')),
  amount NUMERIC(10,2) NOT NULL,
  date DATE NOT NULL,
  description TEXT,
  receipt_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. AUDIT LOGS
CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  performed_by UUID NOT NULL REFERENCES profiles(id),
  action TEXT NOT NULL,
  table_name TEXT NOT NULL,
  record_id UUID NOT NULL,
  old_data JSONB,
  new_data JSONB,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- ROW LEVEL SECURITY (RLS) POLICIES
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE buildings ENABLE ROW LEVEL SECURITY;
ALTER TABLE units ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE occupancy_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Allow user to view and update their own profile
CREATE POLICY "Users can manage own profile" ON profiles
  FOR ALL USING (id = auth.uid()) WITH CHECK (id = auth.uid());

-- Landlords can CRUD their own buildings
CREATE POLICY "Landlords can CRUD their own buildings" ON buildings
  FOR ALL USING (landlord_id = auth.uid()) WITH CHECK (landlord_id = auth.uid());

-- Units policy via building's landlord_id
CREATE POLICY "Landlords manage units via buildings" ON units
  FOR ALL USING (
    building_id IN (SELECT id FROM buildings WHERE landlord_id = auth.uid())
  );

-- Tenants policy via building's landlord_id
CREATE POLICY "Landlords manage tenants via units" ON tenants
  FOR ALL USING (
    unit_id IN (
      SELECT u.id FROM units u 
      JOIN buildings b ON u.building_id = b.id 
      WHERE b.landlord_id = auth.uid()
    )
  );

-- Payments policy via building's landlord_id
CREATE POLICY "Landlords manage payments via units" ON payments
  FOR ALL USING (
    unit_id IN (
      SELECT u.id FROM units u 
      JOIN buildings b ON u.building_id = b.id 
      WHERE b.landlord_id = auth.uid()
    )
  );

-- Public can submit pending payments (for tenant-submit page)
CREATE POLICY "Public can submit pending payments" ON payments
  FOR INSERT WITH CHECK (status = 'pending');

-- Expenses policy
CREATE POLICY "Landlords manage expenses via buildings" ON expenses
  FOR ALL USING (
    building_id IN (SELECT id FROM buildings WHERE landlord_id = auth.uid())
  );

-- Occupancy logs policy
CREATE POLICY "Users manage occupancy logs" ON occupancy_logs
  FOR ALL USING (performed_by = auth.uid());

-- Audit logs policy
CREATE POLICY "Users view audit logs" ON audit_logs
  FOR ALL USING (performed_by = auth.uid());

-- 10. SYSTEM SETTINGS (For landing page custom copy)
CREATE TABLE IF NOT EXISTS system_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- RLS
ALTER TABLE system_settings ENABLE ROW LEVEL SECURITY;

-- Everyone can view system settings
CREATE POLICY "Anyone can view system settings" ON system_settings
  FOR SELECT USING (true);

-- Landlords can update system settings
CREATE POLICY "Landlords can update system settings" ON system_settings
  FOR ALL USING (auth.role() = 'authenticated') WITH CHECK (auth.role() = 'authenticated');

-- Seed initial data
INSERT INTO system_settings (key, value) VALUES
  ('copyright_text', '© 2026 Nairobi Rentals . All rights reserved.'),
  ('philosophy_title', 'Redefining Nairobi property management with quiet elegance.'),
  ('philosophy_description', 'We combine digital automated M-Pesa ledger reconciliation with refined tenant services. Designed specifically for Nairobi landlords overseeing portfolios up to 1,000 units with zero friction and 100% email clarity.'),
  ('stat1_value', '1,000+'),
  ('stat1_label', 'Units Managed'),
  ('stat2_value', '98.4%'),
  ('stat2_label', 'Occupancy Rate'),
  ('stat3_value', 'KES 45M+'),
  ('stat3_label', 'Annual Revenue'),
  ('phil_quote', '“Nairobi Rentals made managing 40 units feel effortless — receipts go out automatically.”'),
  ('phil_quote_author', 'SANAA LANDLORDS GROUP • KILELESHWA'),
  ('why_headline', 'Every unit. Every payment. Every tenant — in one elegant, email-driven portal.'),
  ('why_stat1_val', '100%'),
  ('why_stat1_lbl', 'Email-First'),
  ('why_stat2_val', 'M-Pesa'),
  ('why_stat2_lbl', 'Auto-Ledger')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;


-- Production remediation migration (run in Supabase SQL Editor before deploying).
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS lease_end_date DATE;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS landlord_id UUID REFERENCES profiles(id);
CREATE TABLE IF NOT EXISTS landlord_settings (
  landlord_id UUID PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
  rent_due_day SMALLINT NOT NULL DEFAULT 5 CHECK (rent_due_day BETWEEN 1 AND 28),
  reminder_days_before SMALLINT NOT NULL DEFAULT 3 CHECK (reminder_days_before BETWEEN 0 AND 30),
  late_fee_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
  payment_instructions TEXT NOT NULL DEFAULT '',
  support_email TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS maintenance_requests (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE, title TEXT NOT NULL, description TEXT NOT NULL,
 photo_path TEXT, status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','closed')),
 assignee_name TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS announcements (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), landlord_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
 title TEXT NOT NULL, body TEXT NOT NULL, audience_tenant_ids UUID[] NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS leases (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 unit_id UUID NOT NULL REFERENCES units(id), landlord_id UUID NOT NULL REFERENCES profiles(id), start_date DATE NOT NULL, end_date DATE NOT NULL,
 status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','renewed','terminated','ended')), document_path TEXT, move_in_notes TEXT, move_out_notes TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS privacy_requests (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 request_type TEXT NOT NULL CHECK (request_type IN ('correction','deletion')), message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
ALTER TABLE landlord_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE maintenance_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE announcements ENABLE ROW LEVEL SECURITY;
ALTER TABLE leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_requests ENABLE ROW LEVEL SECURITY;
-- Do not use the Supabase service-role key in browser or customer-facing requests.
-- Deploy policies only after migrating app authentication to Supabase Auth so auth.uid() is populated.
