import os
from pathlib import Path
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.routes import auth, buildings, tenants, payments, occupancy, expenses, reports, demo
from api.services.auth_middleware import get_current_user

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Nairobi Rental Management SaaS API",
    description="Email-First Property Management Platform API for Nairobi Landlords",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

# Rate-limited Auth endpoints wrapper
@app.post("/api/auth/login")
@limiter.limit("5/minute")
def rate_limited_login(request: Request, req: auth.UserLoginRequest, response: Response):
    return auth.login(req, response)

@app.post("/api/auth/register")
@limiter.limit("3/minute")
def rate_limited_register(request: Request, req: auth.UserRegisterRequest, response: Response):
    return auth.register(req, response)

@app.post("/api/auth/forgot-password")
@limiter.limit("3/minute")
def rate_limited_forgot_password(request: Request, req: dict):
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
    "dashboard.html": ["landlord"],
    "reports.html": ["landlord"],
    "expenses.html": ["landlord"],
    "payments.html": ["landlord", "caretaker"],
    "caretaker.html": ["caretaker"],
    "tenant-portal.html": ["tenant"],
}

PUBLIC_DIR = Path(__file__).parent.parent / "public"

@app.get("/{page_name}")
async def serve_protected_page(page_name: str, request: Request):
    if page_name in PAGE_ROLE_REQUIREMENTS:
        # Check authentication server-side
        try:
            user = get_current_user(request, credentials=None)
            required_roles = PAGE_ROLE_REQUIREMENTS[page_name]
            if user.get("role") not in required_roles:
                return RedirectResponse(url="/index.html?error=unauthorized", status_code=302)
        except HTTPException:
            return RedirectResponse(url="/index.html?error=login_required", status_code=302)

    file_path = PUBLIC_DIR / page_name
    if file_path.is_file():
        return FileResponse(file_path)
    
    # Fallback to index.html
    return FileResponse(PUBLIC_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
