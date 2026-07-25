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


@app.post("/api/setup-db")
def setup_database():
    """
    One-time endpoint to apply all required schema migrations to Supabase.
    Safe to call multiple times — all operations are idempotent.
    """
    import os
    results = []
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    if not url or not key or "your-project" in url:
        return {"status": "skipped", "reason": "No real Supabase credentials configured."}

    migrations = [
        "ALTER TABLE buildings ALTER COLUMN landlord_id DROP NOT NULL",
        "ALTER TABLE tenants ALTER COLUMN unit_id DROP NOT NULL",
        "ALTER TABLE tenants ALTER COLUMN lease_start_date DROP NOT NULL",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS password TEXT",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT FALSE",
        "ALTER TABLE units ALTER COLUMN building_id DROP NOT NULL",
    ]

    try:
        from supabase import create_client
        client = create_client(url, key)
        for sql in migrations:
            try:
                client.postgrest.session.post(
                    f"{url}/rest/v1/rpc/exec_sql",
                    json={"query": sql},
                    headers={
                        "apikey": key,
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    }
                )
                results.append({"sql": sql[:60], "status": "applied"})
            except Exception as e:
                results.append({"sql": sql[:60], "status": "skipped", "reason": str(e)[:80]})
    except Exception as e:
        return {"status": "error", "detail": str(e)}

    return {"status": "done", "migrations": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
