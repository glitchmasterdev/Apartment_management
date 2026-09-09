-- Payment operations: per-building instructions, follow-ups, and audit trail.
CREATE TABLE IF NOT EXISTS public.building_payment_settings (
  building_id UUID PRIMARY KEY REFERENCES public.buildings(id) ON DELETE CASCADE,
  payment_method TEXT NOT NULL DEFAULT 'safaricom_paybill' CHECK (payment_method IN ('safaricom_paybill','safaricom_till','mobile_money','bank_transfer')),
  payment_identifier TEXT NOT NULL DEFAULT '',
  payment_account_name TEXT NOT NULL DEFAULT '',
  payment_instructions TEXT NOT NULL DEFAULT '',
  bank_details TEXT NOT NULL DEFAULT '',
  updated_by UUID,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.payment_follow_ups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  unit_id UUID NOT NULL REFERENCES public.units(id) ON DELETE CASCADE,
  staff_id UUID,
  note TEXT NOT NULL,
  promise_to_pay_date DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS payment_follow_ups_tenant_idx ON public.payment_follow_ups (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id TEXT,
  actor_role TEXT,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Support projects that already have an older, smaller audit_logs table.
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS actor_id TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS actor_role TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS action TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS entity_type TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS entity_id TEXT;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.audit_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS audit_logs_entity_idx ON public.audit_logs (entity_type, entity_id, created_at DESC);
