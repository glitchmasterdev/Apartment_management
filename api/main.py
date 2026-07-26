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

# CORS Lockdown
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

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# In-Memory Rate Limiting
_rate_limit_store = defaultdict(list)

def enforce_rate_limit(request: Request, max_requests: int = 5, window_seconds: int = 60):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    timestamps = [t for t in _rate_limit_store[client_ip] if now - t < window_seconds]
    _rate_limit_store[client_ip] = timestamps
    if len(timestamps) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    _rate_limit_store[client_ip].append(now)

# Rate-limited Auth endpoints wrapper
@app.post("/api/auth/login")
def rate_limited_login(request: Request, req: auth.UserLoginRequest, response: Response):
    enforce_rate_limit(request, max_requests=5, window_seconds=60)
    return auth.login(req, response)

@app.post("/api/auth/register")
def rate_limited_register(request: Request, req: auth.UserRegisterRequest, response: Response):
    enforce_rate_limit(request, max_requests=3, window_seconds=60)
    return auth.register(req, response)

@app.post("/api/auth/forgot-password")
def rate_limited_forgot_password(request: Request, req: dict):
    enforce_rate_limit(request, max_requests=3, window_seconds=60)
    return auth.forgot_password(req)

# Include Routers
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

# ── Protected Page Routes (Server-side Auth Enforcement) ──
PAGE_ROLE_REQUIREMENTS = {
    "dashboard": ["landlord"],
    "reports": ["landlord"],
    "expenses": ["landlord"],
    "payments": ["landlord", "caretaker"],
    "caretaker": ["caretaker"],
    "tenant-portal": ["tenant"],
}

PUBLIC_DIR = Path(__file__).parent.parent / "public"

@app.get("/{page_name}")
async def serve_protected_page(page_name: str, request: Request):
    clean_name = page_name.replace(".html", "").strip("/")
    if clean_name in PAGE_ROLE_REQUIREMENTS:
        try:
            user = get_current_user(request, credentials=None)
            required_roles = PAGE_ROLE_REQUIREMENTS[clean_name]
            if user.get("role") not in required_roles:
                return RedirectResponse(url="/index.html?error=unauthorized", status_code=302)
        except HTTPException:
            return RedirectResponse(url="/index.html?error=login_required", status_code=302)

    html_file = PUBLIC_DIR / f"{clean_name}.html"
    if html_file.is_file():
        return FileResponse(html_file)

    file_path = PUBLIC_DIR / page_name
    if file_path.is_file():
        return FileResponse(file_path)

    return FileResponse(PUBLIC_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
