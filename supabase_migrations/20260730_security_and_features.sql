-- MANUAL EXECUTION REQUIRED: run in the Supabase SQL Editor before deploying.
-- This migration does not create buckets or alter live credentials.

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS landlord_id UUID REFERENCES profiles(id);
-- Plaintext passwords must be removed only after every existing user resets
-- their password. The application no longer reads this column.
-- ALTER TABLE tenants DROP COLUMN password;

ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_role_check;
ALTER TABLE profiles ADD CONSTRAINT profiles_role_check CHECK (role IN ('landlord','caretaker','tenant'));
CREATE TABLE IF NOT EXISTS caretaker_properties (
  caretaker_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
  PRIMARY KEY(caretaker_id, building_id)
);
CREATE TABLE IF NOT EXISTS landlord_settings (
 landlord_id UUID PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
 rent_due_day SMALLINT NOT NULL DEFAULT 5 CHECK (rent_due_day BETWEEN 1 AND 28),
 reminder_days_before SMALLINT NOT NULL DEFAULT 3 CHECK (reminder_days_before BETWEEN 0 AND 30),
 reminder_interval_days SMALLINT NOT NULL DEFAULT 1 CHECK (reminder_interval_days BETWEEN 1 AND 31),
 late_fee_amount NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (late_fee_amount >= 0),
 notification_email TEXT NOT NULL DEFAULT '', payment_instructions TEXT NOT NULL DEFAULT '',
 bank_details TEXT NOT NULL DEFAULT '', till_number TEXT NOT NULL DEFAULT '', updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS maintenance_requests (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE, title TEXT NOT NULL, description TEXT NOT NULL,
 photo_path TEXT, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_progress','closed')),
 assignee_name TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS announcements (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), landlord_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
 building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE, title TEXT NOT NULL, body TEXT NOT NULL,
 audience_tenant_ids UUID[], created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS leases (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 unit_id UUID NOT NULL REFERENCES units(id), landlord_id UUID NOT NULL REFERENCES profiles(id), start_date DATE NOT NULL,
 end_date DATE NOT NULL, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN('active','renewed','terminated','ended')),
 document_path TEXT, move_in_notes TEXT, move_out_notes TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), CHECK(end_date > start_date)
);
CREATE TABLE IF NOT EXISTS privacy_requests (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
 landlord_id UUID REFERENCES profiles(id), request_type TEXT NOT NULL CHECK(request_type IN('correction','deletion')),
 message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RLS is designed for Supabase Auth. Application users must be auth.users IDs.
ALTER TABLE caretaker_properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE landlord_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE maintenance_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE announcements ENABLE ROW LEVEL SECURITY;
ALTER TABLE leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_requests ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.can_access_building(target UUID) RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM buildings b WHERE b.id=target AND b.landlord_id=auth.uid())
 OR EXISTS(SELECT 1 FROM caretaker_properties cp WHERE cp.building_id=target AND cp.caretaker_id=auth.uid()) $$;
CREATE OR REPLACE FUNCTION public.can_access_unit(target UUID) RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
 SELECT EXISTS(SELECT 1 FROM units u WHERE u.id=target AND can_access_building(u.building_id)) $$;

DROP POLICY IF EXISTS "tenant own record" ON tenants;
CREATE POLICY "tenant own record" ON tenants FOR SELECT USING (id=auth.uid() OR can_access_unit(unit_id));
DROP POLICY IF EXISTS "tenant own payments" ON payments;
CREATE POLICY "tenant own payments" ON payments FOR SELECT USING (tenant_id=auth.uid() OR can_access_unit(unit_id));
CREATE POLICY "staff scoped payments" ON payments FOR ALL USING (can_access_unit(unit_id)) WITH CHECK (can_access_unit(unit_id));
CREATE POLICY "tenant submits own payments" ON payments FOR INSERT WITH CHECK (tenant_id=auth.uid() AND EXISTS(SELECT 1 FROM tenants t WHERE t.id=auth.uid() AND t.unit_id=payments.unit_id));
CREATE POLICY "staff scoped maintenance" ON maintenance_requests FOR ALL USING (can_access_unit(unit_id)) WITH CHECK (can_access_unit(unit_id));
CREATE POLICY "tenant own maintenance" ON maintenance_requests FOR ALL USING (tenant_id=auth.uid()) WITH CHECK (tenant_id=auth.uid());
CREATE POLICY "tenant applicable announcements" ON announcements FOR SELECT USING (can_access_building(building_id) OR (EXISTS(SELECT 1 FROM tenants t JOIN units u ON u.id=t.unit_id WHERE t.id=auth.uid() AND u.building_id=announcements.building_id) AND (audience_tenant_ids IS NULL OR auth.uid()=ANY(audience_tenant_ids))));
CREATE POLICY "landlord announcements" ON announcements FOR ALL USING (landlord_id=auth.uid()) WITH CHECK (landlord_id=auth.uid() AND can_access_building(building_id));
CREATE POLICY "lease access" ON leases FOR SELECT USING (tenant_id=auth.uid() OR can_access_unit(unit_id));
CREATE POLICY "landlord lease writes" ON leases FOR ALL USING (landlord_id=auth.uid()) WITH CHECK (landlord_id=auth.uid() AND can_access_unit(unit_id));
CREATE POLICY "tenant privacy requests" ON privacy_requests FOR ALL USING (tenant_id=auth.uid()) WITH CHECK (tenant_id=auth.uid());
CREATE POLICY "landlord privacy requests" ON privacy_requests FOR SELECT USING (landlord_id=auth.uid());
CREATE POLICY "landlord settings" ON landlord_settings FOR ALL USING (landlord_id=auth.uid()) WITH CHECK (landlord_id=auth.uid());

-- Create private buckets manually: maintenance-photos and lease-documents.
-- Storage object names must start with maintenance/<tenant-auth-uuid>/ and
-- leases/<landlord-auth-uuid>/ respectively; add matching storage.objects RLS.
