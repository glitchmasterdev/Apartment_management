# Nairobi Rentals — Security Audit Report

**Date**: July 26, 2026  
**Target Application**: Nairobi Rentals (Property Management SaaS)  
**Scope**: Authentication, Authorization, Access Control, Data Protection, API Hardening  

---

## Executive Summary

A security audit of the Nairobi Rentals codebase was conducted to identify vulnerabilities in access control, data handling, authentication, and operational hygiene.

Priorities evaluated:
- **Priority 0**: Critical Broken Access Control (Direct page fetch & API data leaks)
- **Priority 1**: Security Hardening (JWTs, Cookies, Headers, Rate Limiting, M-Pesa Fraud Prevention, KDPA Compliance)

---

## Audit Findings Matrix

| ID | Title | Severity | CVSS 3.1 | Status | Owner |
|---|---|---|---|---|---|
| **SEC-001** | Broken Access Control on Protected Pages (`dashboard.html`, `payments.html`) | Critical | 8.6 | **Resolved** | Backend Lead |
| **SEC-002** | Unauthenticated API Endpoints Exposing Tenant PII & Payment Data | Critical | 9.1 | **Resolved** | Backend Lead |
| **SEC-003** | LocalStorage Session Storage & Lack of Server-Side Session Validation | High | 7.5 | In Progress | Auth / Frontend Lead |
| **SEC-004** | Manual Tenant-Typed M-Pesa Transaction Code Submission (Fraud Risk) | High | 7.4 | Open | Integration Lead |
| **SEC-005** | Missing Security Headers & Wildcard CORS Policy | Medium | 5.3 | In Progress | DevOps Lead |
| **SEC-006** | User Enumeration Risk in Password Reset Flow | Medium | 4.3 | In Progress | Auth Lead |
| **SEC-007** | Lack of Server-Side File & Field Sanitization on CSV Bulk Import | Medium | 5.3 | In Progress | Backend Lead |
| **SEC-008** | Unencrypted PII Storage & Missing KDPA Compliance Artifacts | Medium | 4.8 | Open | Compliance Lead |

---

## Detailed Vulnerability Analysis

### SEC-001: Broken Access Control on Protected Pages (Priority 0)
- **Severity**: Critical (CVSS 8.6 - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N`)
- **Location**: `public/dashboard.html`, `public/payments.html`, `vercel.json`, `api/main.py`
- **Description**: Direct HTTP GET requests to `/dashboard.html` or `/payments` without authentication cookies or session tokens return the raw HTML shell structure containing UI components (Add Property modal, Bulk Import UI, Approvals Hub table structure). While API data endpoints are protected, static page route matching in `vercel.json` previously allowed requests without `.html` extensions or unauthenticated static requests to bypass server-side page authorization.
- **Remediation**:
  1. Standardize route matching in `vercel.json` to capture all variants (`/dashboard`, `/dashboard.html`, `/payments`, `/payments.html`, etc.) and route them to `api/main.py`.
  2. Normalize route names in `api/main.py` and enforce HttpOnly JWT cookie validation before serving `FileResponse`.
  3. Add an immediate inline `<script>` auth guard in the `<head>` of all protected HTML documents to trigger instantaneous client-side redirect if localStorage session is absent.

---

### SEC-002: Unauthenticated API Endpoints Exposing Tenant PII (Priority 0)
- **Severity**: Critical (CVSS 9.1 - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N`)
- **Location**: `api/routes/tenants.py`, `api/routes/payments.py`, `api/routes/buildings.py`, `api/routes/reports.py`, `api/routes/expenses.py`
- **Description**: API routes previously returned tenant personal identifiable information (full names, phone numbers, email addresses, rent balances, payment history) to unauthenticated requests if no token check dependency was present.
- **Remediation**:
  1. Add `current_user: dict = Depends(require_role(["landlord", "caretaker"]))` to every protected endpoint.
  2. Permanently exclude password fields from all API JSON responses.
  3. Enforce Supabase Row Level Security (RLS) policies on all tables so database queries require valid user context.

---

### SEC-003: LocalStorage Session Storage & Weak Token Lifecycles (Priority 1)
- **Severity**: High (CVSS 7.5 - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:P/A:N`)
- **Location**: `public/app.js`, `api/routes/auth.py`
- **Description**: Storing authentication tokens in `localStorage` makes them susceptible to XSS extraction. 
- **Remediation**:
  1. Issue JWT tokens exclusively inside `HttpOnly`, `Secure`, `SameSite=Lax/Strict` cookies.
  2. Restrict `localStorage` to non-sensitive profile state (user name, role, email) used for UI rendering only.
  3. Implement token rotation with short-lived access tokens (15–30 mins) and server-side cookie deletion on logout.

---

### SEC-004: Manual Tenant-Typed M-Pesa Code Submission (Priority 1)
- **Severity**: High (CVSS 7.4 - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:H/A:N`)
- **Location**: `public/tenant-submit.html`, `api/routes/payments.py`
- **Description**: Relying on tenants to manually type M-Pesa transaction codes allows potential fraud (forged codes, duplicate codes, inspect-element manipulation).
- **Remediation**:
  1. Integrate Safaricom Daraja C2B / STK Push webhooks for direct, automated M-Pesa payment confirmation.
  2. Verify webhook signatures using Safaricom shortcode passkeys.
  3. Retain manual code submission strictly as an exceptional fallback path requiring landlord approval.

---

### SEC-005: Missing Security Headers & Wildcard CORS Policy (Priority 1)
- **Severity**: Medium (CVSS 5.3 - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N`)
- **Location**: `vercel.json`, `api/main.py`
- **Description**: Absence of HTTP security headers (CSP, HSTS, X-Frame-Options, Referrer-Policy) and permissive CORS configuration exposes the application to clickjacking, MIME-sniffing, and cross-origin abuse.
- **Remediation**:
  1. Configure strict security headers in `vercel.json` and FastAPI middleware.
  2. Restrict CORS `allow_origins` to production domain(s) and local development hosts.

---

### SEC-006: User Enumeration Leak in Password Reset Flow (Priority 1)
- **Severity**: Medium (CVSS 4.3 - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N`)
- **Location**: `api/routes/auth.py`
- **Description**: Different API response messages for registered vs unregistered emails during password reset requests allow attackers to harvest valid user emails.
- **Remediation**: Return a generic success message ("If that email is registered, a password reset link has been sent") regardless of whether the email exists in the database.

---

### SEC-007: Unsanitized CSV Import & File Upload Vulnerabilities (Priority 1)
- **Severity**: Medium (CVSS 5.3 - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:L`)
- **Location**: `api/routes/buildings.py` (`bulk_import_units`)
- **Description**: Untrusted CSV files uploaded by users could contain formula injection payloads (`=cmd|' /C ...'`), excessive row counts, or malicious cell strings.
- **Remediation**: Enforce a 500-row limit, validate column headers against a strict whitelist, and sanitize cell text server-side.

---

### SEC-008: Kenya Data Protection Act (KDPA 2019) Non-Compliance (Priority 1)
- **Severity**: Medium (CVSS 4.8 - `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N`)
- **Location**: Legal / Data Architecture
- **Description**: Storing tenant PII (phone numbers, national IDs, lease contracts) without formal ODPC registration, consent mechanisms, or explicit export/deletion options risks regulatory non-compliance.
- **Remediation**:
  1. Add `/privacy`, `/terms`, and `/dpa` static pages.
  2. Implement data export (`GET /api/tenants/me/export`) and deletion (`DELETE /api/tenants/me`) endpoints.
  3. Encrypt sensitive PII fields in PostgreSQL using `pgcrypto`.
