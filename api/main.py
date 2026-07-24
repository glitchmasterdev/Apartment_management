from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import auth, buildings, tenants, payments, occupancy, expenses, reports

app = FastAPI(
    title="Nairobi Rental Management SaaS API",
    description="Email-First Property Management Platform API for Nairobi Landlords",
    version="1.0.0"
)

# Enable CORS for local testing and Vercel hosting
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router, prefix="/api")
app.include_router(buildings.router, prefix="/api")
app.include_router(tenants.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(occupancy.router, prefix="/api")
app.include_router(expenses.router, prefix="/api")
app.include_router(reports.router, prefix="/api")

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
