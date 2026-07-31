-- Gap-closure schema updates. Run once in the Supabase SQL editor.
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS verification_token TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS verification_token_expires TIMESTAMPTZ;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS emergency_contact TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS emergency_phone TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS lease_end_date DATE;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS deposit_amount NUMERIC(12,2) DEFAULT 0;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS deposit_returned BOOLEAN DEFAULT FALSE;
ALTER TABLE maintenance_requests ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE maintenance_requests ADD COLUMN IF NOT EXISTS urgency TEXT DEFAULT 'routine';
ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS user_table TEXT NOT NULL DEFAULT 'tenants';
ALTER TABLE privacy_requests DROP CONSTRAINT IF EXISTS privacy_requests_request_type_check;
ALTER TABLE privacy_requests ADD CONSTRAINT privacy_requests_request_type_check CHECK (request_type IN ('access', 'correction', 'deletion'));
DO $$ BEGIN
  ALTER TABLE payments ADD CONSTRAINT payments_mpesa_code_unique UNIQUE (mpesa_code);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE TABLE IF NOT EXISTS login_attempts (ip TEXT PRIMARY KEY, attempt_count INTEGER DEFAULT 0, locked_until TIMESTAMPTZ, last_attempt TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS email_verification_tokens (token TEXT PRIMARY KEY, email TEXT NOT NULL, user_table TEXT NOT NULL DEFAULT 'tenants', expires_at TIMESTAMPTZ NOT NULL, used BOOLEAN DEFAULT FALSE);
