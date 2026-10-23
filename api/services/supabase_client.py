"""Supabase client factory for trusted server-side API routes.

Uses postgrest-py directly to bypass the gotrue-py auth session manager,
which tries to persist tokens to the filesystem and triggers
[Errno 16] Device or resource busy in Vercel's read-only serverless sandbox.
"""
from api.config import settings


def get_supabase_client(access_token: str | None = None):
    """Return a thin wrapper that exposes the same .table() interface
    the rest of the app uses, backed directly by postgrest-py so that
    no gotrue / file-storage machinery is involved.
    """
    api_key = settings.SUPABASE_SECRET_KEY or settings.SUPABASE_ANON_KEY
    if not settings.SUPABASE_URL or not api_key:
        raise RuntimeError("Supabase is not configured")

    # Try the standard supabase client first (works in non-serverless envs)
    # but wrap it so we can fall back to raw postgrest on Errno 16.
    try:
        from supabase import create_client, ClientOptions
        options = ClientOptions(
            postgrest_client_timeout=15,
            storage_client_timeout=15,
            auto_refresh_token=False,
            persist_session=False,
        )
        client = create_client(settings.SUPABASE_URL, api_key, options=options)
        return client
    except Exception:
        pass

    # Fallback: use postgrest-py directly (no gotrue, no file I/O)
    return _make_postgrest_client(settings.SUPABASE_URL, api_key)


def _make_postgrest_client(url: str, api_key: str):
    """Minimal postgrest wrapper with the same .table(name) interface."""
    from postgrest import SyncPostgrestClient

    rest_url = url.rstrip("/") + "/rest/v1"
    headers = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    pg = SyncPostgrestClient(rest_url, headers=headers, timeout=15)

    class _SupabaseCompat:
        """Quacks like a supabase client for .table() calls."""
        def table(self, name: str):
            return pg.from_(name)

    return _SupabaseCompat()
