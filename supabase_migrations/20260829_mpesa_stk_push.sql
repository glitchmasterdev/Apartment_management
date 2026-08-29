-- Safaricom Daraja STK Push audit and idempotency fields.
ALTER TABLE public.payments ADD COLUMN IF NOT EXISTS mpesa_checkout_request_id TEXT;
ALTER TABLE public.payments ADD COLUMN IF NOT EXISTS mpesa_merchant_request_id TEXT;
ALTER TABLE public.payments ADD COLUMN IF NOT EXISTS mpesa_phone_number TEXT;
ALTER TABLE public.payments ADD COLUMN IF NOT EXISTS mpesa_callback_payload JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS payments_checkout_request_id_unique
  ON public.payments (mpesa_checkout_request_id)
  WHERE mpesa_checkout_request_id IS NOT NULL;

-- Record failures as well as successful callbacks; no browser-provided code can
-- produce an approved payment.
ALTER TABLE public.payments DROP CONSTRAINT IF EXISTS payments_status_check;
ALTER TABLE public.payments ADD CONSTRAINT payments_status_check
  CHECK (status IN ('initiated', 'pending', 'approved', 'rejected', 'failed'));
