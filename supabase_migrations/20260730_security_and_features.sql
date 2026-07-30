-- ============================================================
-- Apartment Management — Supabase Database Migration
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ============================================================

-- 1. Ensure required columns exist on tenants
ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS landlord_id UUID REFERENCES public.landlords(id);

-- 2. Caretaker Properties table
CREATE TABLE IF NOT EXISTS public.caretaker_properties (
  caretaker_id UUID NOT NULL REFERENCES public.caretakers(id) ON DELETE CASCADE,
  building_id UUID NOT NULL REFERENCES public.buildings(id) ON DELETE CASCADE,
  PRIMARY KEY(caretaker_id, building_id)
);

-- 3. Landlord Settings table
CREATE TABLE IF NOT EXISTS public.landlord_settings (
  landlord_id UUID PRIMARY KEY REFERENCES public.landlords(id) ON DELETE CASCADE,
  rent_due_day SMALLINT NOT NULL DEFAULT 5 CHECK (rent_due_day BETWEEN 1 AND 28),
  reminder_days_before SMALLINT NOT NULL DEFAULT 3 CHECK (reminder_days_before BETWEEN 0 AND 30),
  reminder_interval_days SMALLINT NOT NULL DEFAULT 1 CHECK (reminder_interval_days BETWEEN 1 AND 31),
  late_fee_amount NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (late_fee_amount >= 0),
  notification_email TEXT NOT NULL DEFAULT '',
  payment_instructions TEXT NOT NULL DEFAULT '',
  bank_details TEXT NOT NULL DEFAULT '',
  till_number TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. Maintenance Requests table
CREATE TABLE IF NOT EXISTS public.maintenance_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  unit_id UUID NOT NULL REFERENCES public.units(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  photo_path TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_progress','closed')),
  assignee_name TEXT DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Announcements table
CREATE TABLE IF NOT EXISTS public.announcements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  landlord_id UUID NOT NULL REFERENCES public.landlords(id) ON DELETE CASCADE,
  building_id UUID NOT NULL REFERENCES public.buildings(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  audience_tenant_ids UUID[],
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. Leases table
CREATE TABLE IF NOT EXISTS public.leases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  unit_id UUID NOT NULL REFERENCES public.units(id),
  landlord_id UUID NOT NULL REFERENCES public.landlords(id),
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN('active','renewed','terminated','ended')),
  document_path TEXT DEFAULT '',
  move_in_notes TEXT DEFAULT '',
  move_out_notes TEXT DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK(end_date > start_date)
);

-- 7. Privacy Requests table
CREATE TABLE IF NOT EXISTS public.privacy_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  landlord_id UUID REFERENCES public.landlords(id),
  request_type TEXT NOT NULL CHECK(request_type IN('correction','deletion')),
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. Disable RLS (app uses service role key)
ALTER TABLE public.caretaker_properties DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.landlord_settings   DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.maintenance_requests DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.announcements         DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.leases                DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.privacy_requests      DISABLE ROW LEVEL SECURITY;
