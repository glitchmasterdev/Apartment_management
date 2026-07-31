"""Supabase client factory for trusted server-side API routes."""
from api.config import settings


def get_supabase_client(access_token: str | None = None):
    """Create a backend client.

    Application JWTs are not Supabase Auth JWTs, so forwarding them to
    PostgREST would make RLS reject valid application requests. The server
    instead uses its server-only key and enforces access in route helpers.
    """
    api_key = settings.SUPABASE_SECRET_KEY or settings.SUPABASE_ANON_KEY
    if not settings.SUPABASE_URL or not api_key:
        raise RuntimeError("Supabase is not configured")
    from supabase import create_client

    return create_client(settings.SUPABASE_URL, api_key)
