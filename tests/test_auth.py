"""HTTP integration checks. Set TEST_API_URL and TEST_TENANT_EMAIL/PASSWORD to run them."""
import os
import pytest
import httpx

BASE_URL = os.getenv("TEST_API_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="Set TEST_API_URL for integration tests")

def client(): return httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=15)
def tenant_credentials(): return {"email": os.environ["TEST_TENANT_EMAIL"], "password": os.environ["TEST_TENANT_PASSWORD"], "expected_role":"tenant"}

def test_register_tenant():
    pytest.skip("Requires disposable tenant fixture and mail sandbox")
def test_register_duplicate_email():
    pytest.skip("Requires disposable tenant fixture")

def test_login_valid_tenant():
    with client() as c:
        response=c.post("/api/auth/login", json=tenant_credentials())
        assert response.status_code == 200 and "nrb_token" in c.cookies

def test_login_wrong_password():
    data=tenant_credentials(); data["password"]="not-the-password1"
    with client() as c: assert c.post("/api/auth/login", json=data).status_code == 401

def test_login_lockout():
    pytest.skip("Run only with a dedicated TEST_CLIENT_IP environment")

def test_tenant_cannot_access_staff_dashboard():
    with client() as c:
        assert c.post("/api/auth/login",json=tenant_credentials()).status_code == 200
        assert c.get("/api/tenants").status_code == 403

def test_staff_cannot_use_tenant_portal():
    pytest.skip("Requires configured TEST_LANDLORD_EMAIL/PASSWORD")
def test_payment_submit_requires_auth():
    with client() as c: assert c.post("/api/payments",json={"amount":100,"mpesa_code":"TESTNOAUTH"}).status_code == 401
def test_payment_submit_duplicate_mpesa():
    pytest.skip("Requires approved disposable tenant with a unit")
def test_forgot_password_generic_response():
    with client() as c:
        assert c.post("/api/auth/forgot-password",json={"email":"unknown@example.invalid"}).status_code == 200
def test_reset_password_expired_token():
    pytest.skip("Requires expired reset token fixture")
def test_reset_password_already_used():
    pytest.skip("Requires used reset token fixture")
def test_reset_password_writes_correct_column():
    pytest.skip("Requires isolated Supabase test project and service-role inspection")
