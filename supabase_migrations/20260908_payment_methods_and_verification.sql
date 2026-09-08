-- Tenant payment instructions and Safaricom-verification states.
ALTER TABLE public.landlord_settings ADD COLUMN IF NOT EXISTS payment_method TEXT NOT NULL DEFAULT 'safaricom_paybill'
  CHECK (payment_method IN ('safaricom_paybill','safaricom_till','mobile_money','bank_transfer'));
ALTER TABLE public.landlord_settings ADD COLUMN IF NOT EXISTS payment_identifier TEXT NOT NULL DEFAULT '';
ALTER TABLE public.landlord_settings ADD COLUMN IF NOT EXISTS payment_account_name TEXT NOT NULL DEFAULT '';

ALTER TABLE public.payments ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'manual_review'
  CHECK (verification_status IN ('manual_review','unverified_message','safaricom_confirmed','stk_confirmed'));
CREATE INDEX IF NOT EXISTS payments_verification_status_idx ON public.payments (verification_status);
