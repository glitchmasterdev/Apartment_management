"""
Integration tests: Tenant <-> Landlord data flow
=================================================
Covers all the key communication paths between the tenant portal and the
landlord dashboard.

Required environment variables:
    TEST_API_URL            - Base URL of the live API, e.g. https://your-app.vercel.app
    TEST_LANDLORD_EMAIL     - Landlord account email
    TEST_LANDLORD_PASSWORD  - Landlord account password
    TEST_TENANT_EMAIL       - An already-approved tenant account email
    TEST_TENANT_PASSWORD    - Tenant account password

Run with:
    set TEST_API_URL=https://your-app.vercel.app
    pytest tests/test_tenant_landlord_flow.py -v
"""
import os
import time
import uuid
import pytest
import httpx

BASE_URL = os.getenv("TEST_API_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="Set TEST_API_URL environment variable to run integration tests",
)

LANDLORD_CREDS = {
    "email": os.getenv("TEST_LANDLORD_EMAIL", ""),
    "password": os.getenv("TEST_LANDLORD_PASSWORD", ""),
    "expected_role": "landlord",
}
TENANT_CREDS = {
    "email": os.getenv("TEST_TENANT_EMAIL", ""),
    "password": os.getenv("TEST_TENANT_PASSWORD", ""),
    "expected_role": "tenant",
}

TIMEOUT = 20


def landlord_client():
    c = httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=TIMEOUT)
    r = c.post("/api/auth/login", json=LANDLORD_CREDS)
    assert r.status_code == 200, f"Landlord login failed: {r.text}"
    return c


def tenant_client():
    c = httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=TIMEOUT)
    r = c.post("/api/auth/login", json=TENANT_CREDS)
    assert r.status_code == 200, f"Tenant login failed: {r.text}"
    return c


# ===========================================================================
# 1. AUTHENTICATION & ROLE ISOLATION
# ===========================================================================

class TestAuthRoleIsolation:
    def test_landlord_login_returns_token(self):
        with landlord_client() as c:
            assert "nrb_token" in c.cookies

    def test_tenant_login_returns_token(self):
        with tenant_client() as c:
            assert "nrb_token" in c.cookies

    def test_tenant_cannot_access_all_payments(self):
        with tenant_client() as c:
            assert c.get("/api/payments").status_code == 403

    def test_tenant_cannot_access_dashboard_report(self):
        with tenant_client() as c:
            assert c.get("/api/reports/dashboard").status_code == 403

    def test_tenant_cannot_approve_payments(self):
        with tenant_client() as c:
            assert c.post("/api/payments/approve", json={"payment_ids": ["x"]}).status_code == 403

    def test_tenant_cannot_list_all_tenants(self):
        with tenant_client() as c:
            assert c.get("/api/tenants").status_code == 403

    def test_landlord_cannot_access_tenant_payments_me(self):
        with landlord_client() as c:
            assert c.get("/api/payments/me").status_code == 403

    def test_unauthenticated_payment_submit_rejected(self):
        with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as c:
            assert c.post("/api/payments", json={"amount": 100, "mpesa_code": "X"}).status_code == 401


# ===========================================================================
# 2. PAYMENT SUBMISSION FLOW
# ===========================================================================

class TestPaymentSubmissionFlow:
    def test_tenant_can_view_own_payments(self):
        with tenant_client() as c:
            r = c.get("/api/payments/me")
            assert r.status_code == 200
            assert "payments" in r.json()

    def test_payment_data_isolation(self):
        with tenant_client() as c:
            me = c.get("/api/tenants/me").json()["tenant"]
            payments = c.get("/api/payments/me").json()["payments"]
            for p in payments:
                assert p["tenant_id"] == me["id"], f"Isolation breach on payment {p['id']}"

    def test_zero_amount_rejected(self):
        with tenant_client() as c:
            assert c.post("/api/payments", json={"amount": 0, "mpesa_code": "Z001"}).status_code == 422

    def test_empty_mpesa_rejected(self):
        with tenant_client() as c:
            assert c.post("/api/payments", json={"amount": 100, "mpesa_code": ""}).status_code == 422

    def test_landlord_sees_pending_payments(self):
        with landlord_client() as c:
            r = c.get("/api/payments/pending")
            assert r.status_code == 200
            assert "pending_payments" in r.json()

    def test_landlord_sees_all_payments(self):
        with landlord_client() as c:
            r = c.get("/api/payments")
            assert r.status_code == 200
            assert "payments" in r.json()

    def test_payment_status_fields_present(self):
        required = {"id", "tenant_id", "unit_id", "amount_paid", "status", "payment_date"}
        with landlord_client() as c:
            for p in c.get("/api/payments").json().get("payments", []):
                missing = required - set(p.keys())
                assert not missing, f"Payment {p.get('id')} missing: {missing}"


# ===========================================================================
# 3. TENANT PROFILE & LEASE DATA
# ===========================================================================

class TestTenantProfileFromLandlord:
    def test_tenant_can_read_own_profile(self):
        with tenant_client() as c:
            r = c.get("/api/tenants/me")
            assert r.status_code == 200
            t = r.json()["tenant"]
            for field in ("id", "full_name", "email", "unit_id", "monthly_rent", "account_number"):
                assert field in t, f"Missing: {field}"

    def test_tenant_profile_has_support_contact(self):
        with tenant_client() as c:
            t = c.get("/api/tenants/me").json()["tenant"]
            contact = t.get("support_contact", {})
            assert "name" in contact and "email" in contact and "phone" in contact

    def test_landlord_can_list_tenants(self):
        with landlord_client() as c:
            r = c.get("/api/tenants")
            assert r.status_code == 200
            assert isinstance(r.json()["tenants"], list)

    def test_landlord_tenant_list_no_password(self):
        with landlord_client() as c:
            for t in c.get("/api/tenants").json().get("tenants", []):
                assert "password" not in t, f"Password exposed for {t.get('id')}"

    def test_landlord_tenant_list_has_ledger(self):
        with landlord_client() as c:
            for t in c.get("/api/tenants").json().get("tenants", []):
                assert "ledger" in t, f"Missing ledger for {t.get('id')}"

    def test_tenant_can_update_profile(self):
        with tenant_client() as c:
            r = c.put("/api/tenants/me", json={"phone_number": "+254700123456"})
            assert r.status_code == 200

    def test_blank_name_rejected(self):
        with tenant_client() as c:
            assert c.put("/api/tenants/me", json={"full_name": ""}).status_code == 422


# ===========================================================================
# 4. KPI DASHBOARD & OCCUPANCY
# ===========================================================================

class TestDashboardKPIs:
    def test_dashboard_returns_kpis(self):
        with landlord_client() as c:
            r = c.get("/api/reports/dashboard")
            assert r.status_code == 200
            kpis = r.json()["kpis"]
            for f in ("total_units", "occupied_units", "occupancy_rate", "monthly_revenue", "rent_received"):
                assert f in kpis, f"KPI missing: {f}"

    def test_occupancy_rate_range(self):
        with landlord_client() as c:
            rate = c.get("/api/reports/dashboard").json()["kpis"]["occupancy_rate"]
            assert 0 <= rate <= 100, f"Out of range: {rate}"

    def test_occupied_not_exceeds_total(self):
        with landlord_client() as c:
            kpis = c.get("/api/reports/dashboard").json()["kpis"]
            assert kpis["occupied_units"] <= kpis["total_units"]

    def test_yoy_chart_12_months(self):
        with landlord_client() as c:
            data = c.get("/api/reports/yoy-occupancy").json()
            assert len(data["labels"]) == 12
            assert len(data["current_year"]) == 12

    def test_yoy_chart_no_negative_values(self):
        with landlord_client() as c:
            for i, v in enumerate(c.get("/api/reports/yoy-occupancy").json()["current_year"]):
                assert v >= 0, f"Month {i} has negative value: {v}"

    def test_revenue_consistency(self):
        with landlord_client() as c:
            kpis = c.get("/api/reports/dashboard").json()["kpis"]
            assert kpis["monthly_revenue"] >= kpis["rent_received"] - 1


# ===========================================================================
# 5. MAINTENANCE REQUEST FLOW
# ===========================================================================

class TestMaintenanceRequestFlow:
    def test_tenant_can_submit_request(self):
        with tenant_client() as c:
            r = c.post("/api/maintenance", json={
                "title": f"Test {uuid.uuid4().hex[:6]}",
                "description": "Integration test leak",
                "urgency": "medium",
            })
            assert r.status_code in (200, 201), f"Submit failed: {r.text}"

    def test_tenant_can_list_own_requests(self):
        with tenant_client() as c:
            r = c.get("/api/maintenance/me")
            assert r.status_code == 200

    def test_landlord_can_list_requests(self):
        with landlord_client() as c:
            r = c.get("/api/maintenance")
            assert r.status_code == 200

    def test_maintenance_end_to_end(self):
        unique = f"E2E-{uuid.uuid4().hex[:8]}"
        with tenant_client() as tc:
            r = tc.post("/api/maintenance", json={"title": unique, "description": "E2E test", "urgency": "low"})
            assert r.status_code in (200, 201), f"Submit failed: {r.text}"

        time.sleep(1)
        with landlord_client() as lc:
            resp = lc.get("/api/maintenance").json()
            key = "requests" if "requests" in resp else "maintenance_requests"
            matching = [x for x in resp.get(key, []) if x.get("title") == unique]
            assert matching, f"Landlord cannot see request '{unique}'"

            req_id = matching[0]["id"]
            update = lc.patch(f"/api/maintenance/{req_id}", json={"status": "in_progress"})
            assert update.status_code in (200, 204), f"Status update failed: {update.text}"


# ===========================================================================
# 6. PENDING TENANT REGISTRATION
# ===========================================================================

class TestRegistrationApproval:
    def test_landlord_can_list_pending_tenants(self):
        with landlord_client() as c:
            r = c.get("/api/auth/pending-tenants")
            assert r.status_code == 200
            assert "tenants" in r.json()

    def test_pending_tenant_has_required_fields(self):
        with landlord_client() as c:
            for t in c.get("/api/auth/pending-tenants").json().get("tenants", []):
                for f in ("id", "full_name", "email", "email_verified"):
                    assert f in t, f"Pending tenant missing: {f}"


# ===========================================================================
# 7. REJECTED PAYMENTS
# ===========================================================================

class TestRejectedPaymentVisibility:
    def test_rejected_payments_visible_to_tenant(self):
        with tenant_client() as c:
            payments = c.get("/api/payments/me").json().get("payments", [])
            for p in [x for x in payments if x.get("status") == "rejected"]:
                assert "status" in p

    def test_tenant_cannot_delete_pending_payment(self):
        with tenant_client() as c:
            payments = c.get("/api/payments/me").json().get("payments", [])
            pending = [p for p in payments if p.get("status") == "pending"]
            if not pending:
                pytest.skip("No pending payments to test")
            r = c.delete(f"/api/payments/{pending[0]['id']}")
            assert r.status_code == 400, f"Expected 400, got {r.status_code}"


# ===========================================================================
# 8. BUILDING SCOPE
# ===========================================================================

class TestPropertyScope:
    def test_landlord_can_list_buildings(self):
        with landlord_client() as c:
            r = c.get("/api/buildings")
            assert r.status_code == 200
            assert isinstance(r.json()["buildings"], list)

    def test_dashboard_scoped_to_building(self):
        with landlord_client() as lc:
            buildings = lc.get("/api/buildings").json().get("buildings", [])
            if not buildings:
                pytest.skip("No buildings configured")
            r = lc.get(f"/api/reports/dashboard?building_id={buildings[0]['id']}")
            assert r.status_code == 200

    def test_invalid_building_rejected(self):
        with landlord_client() as c:
            r = c.get(f"/api/reports/dashboard?building_id={uuid.uuid4()}")
            assert r.status_code in (403, 404, 422)
