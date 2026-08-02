"""
auth_middleware.py — JWT authentication dependency for FastAPI routes.

Usage:
    from api.services.auth_middleware import get_current_user, require_role

    @router.get("/protected")
    def my_endpoint(current_user: dict = Depends(get_current_user)):
        ...

    @router.get("/landlord-only")
    def landlord_endpoint(current_user: dict = Depends(require_role(["landlord"]))):
        ...
"""
import os
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from api.services.supabase_client import get_supabase_client

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("CRITICAL SECURITY ERROR: SECRET_KEY environment variable is not set!")
ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    Extract and validate a JWT from either:
      1. Authorization: Bearer <token>  header, OR
      2. nrb_token HttpOnly cookie
    Returns the decoded payload dict: {"id", "role", "email", "full_name"}.
    Raises HTTP 401 if missing or invalid.
    """
    token = None

    # Prefer Authorization header
    if credentials and credentials.credentials:
        token = credentials.credentials
    else:
        # Direct calls to this dependency (for example, protected page
        # rendering) do not have FastAPI's HTTPBearer dependency resolved.
        # Preserve support for a Bearer header before falling back to the
        # browser's HttpOnly session cookie.
        authorization = request.headers.get("authorization", "")
        scheme, _, bearer_token = authorization.partition(" ")
        if scheme.lower() == "bearer" and bearer_token:
            token = bearer_token
        else:
            token = request.cookies.get("nrb_token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in.",
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # A JWT is otherwise valid until it expires.  Confirm a tenant still
        # exists on every protected request so deleting the tenant immediately
        # revokes an already-issued session.  Moved-out tenants still have a
        # row and are therefore allowed to keep using their account.
        if payload.get("role") == "tenant":
            try:
                db = get_supabase_client()
                if hasattr(db, "tenants"):
                    exists = any(str(t.get("id")) == str(payload.get("id")) for t in db.tenants)
                else:
                    rows = db.table("tenants").select("id").eq("id", payload.get("id")).limit(1).execute().data
                    exists = bool(rows)
            except Exception:
                raise HTTPException(
                    status_code=503,
                    detail="Session validation is temporarily unavailable. Please try again.",
                )
            if not exists:
                raise HTTPException(
                    status_code=401,
                    detail="This tenant account has been deleted. Please sign in with an active account.",
                )
        return payload
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid. Please sign in again.",
        )


def require_role(allowed_roles: list):
    """
    Factory that returns a FastAPI dependency enforcing role membership.
    Example: Depends(require_role(["landlord", "caretaker"]))
    """
    def _check(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. This action requires one of: {', '.join(allowed_roles)}.",
            )
        return current_user
    return _check
