# Manual Test Checklist — Apartment Management Portal

## Device Testing
- [ ] Chrome desktop, Safari iOS, and Chrome Android
- [ ] 375px, 390px, and 414px widths without horizontal scrolling
- [ ] Dark mode uses a dark green palette and mobile bottom navigation is visible

## Auth and email
- [ ] Tenant sign-up requires consent and receives a verification email
- [ ] Unverified tenants cannot be approved; verified tenants can
- [ ] Five bad sign-ins show a rate-limit message
- [ ] Password reset, verification, welcome, and payment-confirmation emails arrive

## Tenant portal
- [ ] Profile changes, lease details, payment receipt printing, maintenance requests, notices, and privacy requests work
- [ ] A duplicate M-Pesa code shows a friendly error
