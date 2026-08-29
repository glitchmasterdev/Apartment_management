import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # This is a server-side FastAPI application. The privileged key is kept in
    # Vercel only; browser code never receives it. Route-level authorization
    # remains responsible for tenant and staff isolation.
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SECRET_KEY: str = os.getenv("SUPABASE_SECRET_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    # Safaricom Daraja credentials. Keep every one of these server-only.
    MPESA_CONSUMER_KEY: str = os.getenv("MPESA_CONSUMER_KEY", "")
    MPESA_CONSUMER_SECRET: str = os.getenv("MPESA_CONSUMER_SECRET", "")
    MPESA_SHORTCODE: str = os.getenv("MPESA_SHORTCODE", "")
    MPESA_PASSKEY: str = os.getenv("MPESA_PASSKEY", "")
    MPESA_ENVIRONMENT: str = os.getenv("MPESA_ENVIRONMENT", "production").lower()
    MPESA_CALLBACK_SECRET: str = os.getenv("MPESA_CALLBACK_SECRET", "")
    APP_URL: str = os.getenv("APP_URL", "")
    
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@nairobrentals.com")

settings = Settings()
