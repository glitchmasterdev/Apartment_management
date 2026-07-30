"""Supabase client factory for request-scoped, RLS-enforced access."""
from api.config import settings


def get_supabase_client(access_token: str | None = None):
    """Create an anon-key client and bind it to the signed-in user when supplied.

    The service-role key is intentionally not read by application code.  When
    Supabase is unavailable the API fails closed instead of serving mock data.
    """
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        raise RuntimeError("Supabase is not configured")
    from supabase import create_client

    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    if access_token:
        client.postgrest.auth(access_token)
    return client
