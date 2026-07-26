# Priority 0 — Implementation Plan: Auth-Guard Fix & Access Control Consolidation

**Target**: Fix broken access control on `dashboard.html` and `payments.html` (and consolidate all protected page & API route guards).  
**Branch**: `feature/security-audit-and-hardening`  
**Execution Status**: Pending User Approval  

---

## 1. Context & Problem Statement

### Finding
- `dashboard.html` and `payments.html` currently render their HTML structural UI (Add Property modal, CSV Import UI, Approvals Hub table layout) to unauthenticated requests when accessed directly.
- The working pages (`expenses.html`, `reports.html`, `caretaker.html`) correctly redirect unauthenticated visitors to `/index.html?error=login_required`.
- Route matching in `vercel.json` previously allowed URLs missing `.html` (e.g. `GET /dashboard` or `GET /payments`) or static asset fetches to bypass Python server-side page authorization.
- While underlying API endpoints (`/api/tenants`, `/api/payments/pending`) require JWT authorization, the UI shell exposure and potential URL bypasses represent an inconsistent, un-unified guard architecture.

---

## 2. Shared Auth-Guard Strategy (No Copy-Pasted Code)

To prevent future new pages from silently shipping unguarded:

### A. Centralized Vercel Route Matcher (`vercel.json`)
Consolidate all protected HTML routes under a single regex rule that catches all URL variants:
- `/dashboard`, `/dashboard.html`, `/dashboard/`
- `/payments`, `/payments.html`, `/payments/`
- `/expenses`, `/expenses.html`, `/expenses/`
- `/reports`, `/reports.html`, `/reports/`
- `/caretaker`, `/caretaker.html`, `/caretaker/`
- `/tenant-portal`, `/tenant-portal.html`, `/tenant-portal/`

All matchers map to `destination: "api/main.py"`.

### B. Normalized FastAPI Page Middleware (`api/main.py`)
In `api/main.py`, define a single, immutable `PAGE_ROLE_REQUIREMENTS` registry:
```python
PAGE_ROLE_REQUIREMENTS = {
    "dashboard": ["landlord"],
    "reports": ["landlord"],
    "expenses": ["landlord"],
    "payments": ["landlord", "caretaker"],
    "caretaker": ["caretaker"],
    "tenant-portal": ["tenant"],
}
```
`serve_protected_page` will:
1. Strip `.html` and trailing slashes to extract `clean_name`.
2. Check if `clean_name` exists in `PAGE_ROLE_REQUIREMENTS`.
3. Read `nrb_token` HttpOnly cookie or `Authorization` header via `get_current_user(request)`.
4. If unauthenticated or role mismatched → return `RedirectResponse("/index.html?error=login_required", status_code=302)`.
5. If authorized → serve `FileResponse(PUBLIC_DIR / f"{clean_name}.html")`.

### C. Client-Side Immediate `<head>` Script Guard (Layout Wrapper Rule)
Add a standardized, zero-dependency inline script at the top of `<head>` in every protected page (`dashboard.html`, `payments.html`, `expenses.html`, `reports.html`, `caretaker.html`, `tenant-portal.html`):
```html
<script>
  (function() {
    const s = localStorage.getItem('nrb_session');
    if (!s) { window.location.href = 'index.html?error=login_required'; }
  })();
</script>
```
This guarantees instantaneous browser redirection before any DOM elements or body content can render.

---

## 3. Files Touched

| File | Change Summary |
|---|---|
| `vercel.json` | Update regex routes so `/dashboard`, `/payments`, etc. (with or without `.html`) route to `api/main.py`. |
| `api/main.py` | Normalize route path in `serve_protected_page` and enforce cookie JWT verification against `PAGE_ROLE_REQUIREMENTS`. |
| `public/dashboard.html` | Add inline `<head>` auth guard script to match `expenses.html` / `reports.html`. |
| `public/payments.html` | Add inline `<head>` auth guard script to match `expenses.html` / `reports.html`. |
| `public/expenses.html` | Verify inline `<head>` auth guard script & DOMContentLoaded check. |
| `public/reports.html` | Verify inline `<head>` auth guard script & DOMContentLoaded check. |
| `public/caretaker.html` | Verify inline `<head>` auth guard script & DOMContentLoaded check. |
| `public/tenant-portal.html` | Verify inline `<head>` auth guard script & DOMContentLoaded check. |
| `supabase_rls.sql` | Provide complete SQL commands to enable and verify Row Level Security policies on `tenants`, `payments`, `units`, `buildings`, `expenses`. |

---

## 4. Supabase Row Level Security (RLS) Verification Plan

To guarantee data is protected even if a frontend or routing guard is bypassed:

```sql
-- 1. Enable RLS on all tables
ALTER TABLE buildings ENABLE ROW LEVEL SECURITY;
ALTER TABLE units ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;

-- 2. Buildings Policy
CREATE POLICY "Landlords read own buildings" ON buildings
    FOR SELECT USING (auth.uid() = landlord_id OR auth.jwt() ->> 'role' = 'caretaker');

-- 3. Units Policy
CREATE POLICY "Units access policy" ON units
    FOR SELECT USING (
        EXISTS (
            SELECT 1 FROM buildings 
            WHERE buildings.id = units.building_id 
            AND (buildings.landlord_id = auth.uid() OR auth.jwt() ->> 'role' IN ('caretaker', 'tenant'))
        )
    );

-- 4. Tenants Policy
CREATE POLICY "Tenants own data or landlord" ON tenants
    FOR ALL USING (
        id = auth.uid() 
        OR auth.jwt() ->> 'role' IN ('landlord', 'caretaker')
    );

-- 5. Payments Policy
CREATE POLICY "Payments tenant or landlord" ON payments
    FOR ALL USING (
        tenant_id = auth.uid() 
        OR auth.jwt() ->> 'role' IN ('landlord', 'caretaker')
    );
```

---

## 5. New Dependencies

**None**. All implementation uses Python standard library, existing FastAPI dependencies, and standard HTML/JS.

---

## 6. Verification & Validation Steps

1. **Unauthenticated Page Request Test (Curl)**:
   ```bash
   curl -i http://localhost:8000/dashboard
   curl -i http://localhost:8000/dashboard.html
   curl -i http://localhost:8000/payments
   curl -i http://localhost:8000/payments.html
   ```
   *Expected Result*: HTTP 302 Redirect to `/index.html?error=login_required`.

2. **Authenticated Page Request Test (Curl with Cookie)**:
   ```bash
   curl -i -b "nrb_token=<VALID_LANDLORD_JWT>" http://localhost:8000/dashboard.html
   ```
   *Expected Result*: HTTP 200 OK with page HTML content.

3. **Role Mismatch Test (Tenant accessing Dashboard)**:
   ```bash
   curl -i -b "nrb_token=<VALID_TENANT_JWT>" http://localhost:8000/dashboard.html
   ```
   *Expected Result*: HTTP 302 Redirect to `/index.html?error=unauthorized`.

4. **Public Page Verification**:
   - `index.html`, `demo.html`, `units.html`, `tenant-submit.html`, `reset-password.html` remain publicly accessible without login.

---

## 7. Rollback Plan

If any issues occur during testing:
1. Revert modifications on `feature/security-audit-and-hardening`:
   ```bash
   git checkout main -- vercel.json api/main.py public/
   ```
2. No database migrations will be altered that break read access.

---

## 8. Open Questions & Flags for User

> [!NOTE]
> 1. **Public Pages Confirmation**: We have confirmed that `index.html`, `demo.html`, `units.html`, `tenant-submit.html`, and `reset-password.html` are intentionally public. Only `dashboard.html`, `payments.html`, `expenses.html`, `reports.html`, `caretaker.html`, and `tenant-portal.html` will be protected behind authentication. Please confirm if any other page should be public or private.
> 2. **Branch Isolation**: All changes will remain on the git branch `feature/security-audit-and-hardening`. No push to `main` or production deployment will happen without your explicit command.
