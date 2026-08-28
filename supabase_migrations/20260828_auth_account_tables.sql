-- Authentication account tables used by api/routes/auth.py.
-- Run this migration in Supabase SQL Editor before (or alongside) deployment.
-- The API accesses these tables using the server-only service-role key; do not
-- grant anonymous users direct access to password hashes.

CREATE TABLE IF NOT EXISTS public.landlords (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  contact TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.caretakers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  contact TEXT NOT NULL DEFAULT '',
  landlord_id UUID REFERENCES public.landlords(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.landlords ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.caretakers ENABLE ROW LEVEL SECURITY;

-- Requests are served by the API with SUPABASE_SERVICE_ROLE_KEY (or
-- SUPABASE_SECRET_KEY). Keeping no anon/authenticated policy protects account
-- identifiers and password hashes from direct PostgREST access.
