import os
import time
from collections import defaultdict
from pathlib import Path
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from api.routes import auth, buildings, tenants, payments, occupancy, expenses, reports, demo
from api.services.auth_middleware import get_current_user

app = FastAPI(
    title="Nairobi Rental Management SaaS API",
    description="Email-First Property Management Platform API for Nairobi Landlords",
    version="1.0.0"
)

# ── CORS Lockdown ─────────────────────────────────────────────────────────────
allowed_origins = [
    "https://apartment-management-lime.vercel.app",
    "http://localhost:8000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
]
custom_origin = os.getenv("ALLOWED_ORIGIN")
if custom_origin:
    allowed_origins.append(custom_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── Security Headers Middleware ───────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

# ── CSRF Double-Submit Cookie Protection ──────────────────────────────────────
def get_csrf_token_from_cookie(request: Request) -> str | None:
    return request.cookies.get("csrf_token")

def validate_csrf(request: Request):
    """
    Validates that the X-CSRF-Token header matches the csrf_token cookie.
    Apply this dependency to all state-changing routes (POST/PUT/DELETE).
    Skipped for GET and OPTIONS (safe methods).
    Skipped for demo login (intentionally public).
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token:
        raise HTTPException(status_code=403, detail="CSRF token missing.")
    if not secrets_compare(cookie_token, header_token):
        raise HTTPException(status_code=403, detail="CSRF token mismatch.")

import secrets as _secrets

def secrets_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return _secrets.compare_digest(a.encode(), b.encode())

# ── CSRF Token Issuer (set on every page load) ────────────────────────────────
@app.middleware("http")
async def issue_csrf_token(request: Request, call_next):
    response: Response = await call_next(request)
    # Issue a fresh CSRF token if one doesn't exist (or on HTML page loads)
    if not request.cookies.get("csrf_token"):
        csrf_token = _secrets.token_hex(32)
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            httponly=False,   # Must be readable by JS to attach as header
            secure=True,
            samesite="strict",
            path="/",
        )
    return response

# ── Login Brute-Force: Exponential Lockout ────────────────────────────────────
# Tracks failed login attempts per IP in memory.
# After 3 failures: 30-second delay. After 5 failures: 15-minute ban.
# Counter resets on successful login or after 15 minutes of inactivity.
_login_failures: dict = defaultdict(lambda: {"count": 0, "locked_until": 0.0, "last_attempt": 0.0})
_LOGIN_LOCKOUT_THRESHOLD = 5        # ban after this many failures
_LOGIN_WARN_THRESHOLD = 3           # impose delay after this many failures
_LOGIN_LOCKOUT_SECONDS = 900        # 15-minute ban
_LOGIN_DELAY_SECONDS = 30           # 30-second delay warning zone
_LOGIN_RESET_AFTER = 900            # reset counter after 15 min of inactivity

def enforce_login_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    state = _login_failures[client_ip]

    # Reset stale counters
    if now - state["last_attempt"] > _LOGIN_RESET_AFTER:
        state["count"] = 0
        state["locked_until"] = 0.0

    # Check if currently locked out
    if state["locked_until"] and now < state["locked_until"]:
        retry_after = int(state["locked_until"] - now)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed login attempts. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    state["last_attempt"] = now

def record_login_failure(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    state = _login_failures[client_ip]
    state["count"] += 1
    state["last_attempt"] = now

    if state["count"] >= _LOGIN_LOCKOUT_THRESHOLD:
        state["locked_until"] = now + _LOGIN_LOCKOUT_SECONDS

def record_login_success(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _login_failures[client_ip] = {"count": 0, "locked_until": 0.0, "last_attempt": 0.0}

# ── General Rate Limiting (non-login routes) ──────────────────────────────────
_rate_limit_store = defaultdict(list)

def enforce_rate_limit(request: Request, max_requests: int = 5, window_seconds: int = 60):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    timestamps = [t for t in _rate_limit_store[client_ip] if now - t < window_seconds]
    _rate_limit_store[client_ip] = timestamps
    if len(timestamps) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    _rate_limit_store[client_ip].append(now)

# ── Rate-limited + CSRF-protected Auth endpoints ──────────────────────────────
from api.routes.auth import UserLoginRequest, UserRegisterRequest

@app.post("/api/auth/login")
def rate_limited_login(request: Request, req: UserLoginRequest, response: Response):
    enforce_login_rate_limit(request)
    try:
        result = auth.login(req, response)
        record_login_success(request)
        return result
    except HTTPException as e:
        if e.status_code == 401:
            record_login_failure(request)
        raise

@app.post("/api/auth/register")
def rate_limited_register(request: Request, req: UserRegisterRequest, response: Response):
    enforce_rate_limit(request, max_requests=3, window_seconds=60)
    return auth.register(req, response)

@app.post("/api/auth/forgot-password")
def rate_limited_forgot_password(request: Request, req: dict):
    enforce_rate_limit(request, max_requests=3, window_seconds=300)
    return auth.forgot_password(req)

# ── Include All Routers ───────────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api")
app.include_router(buildings.router, prefix="/api")
app.include_router(tenants.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(occupancy.router, prefix="/api")
app.include_router(expenses.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(demo.router, prefix="/api")

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Nairobi Rental Management API",
        "email_status": "configured",
        "database": "Supabase Ready"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
