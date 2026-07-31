document.addEventListener('DOMContentLoaded', () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Setup tab switcher buttons
  const tabLogin = document.getElementById('tp-tab-login');
  if (tabLogin) tabLogin.addEventListener('click', () => showTenantTab('login'));

  const tabSignup = document.getElementById('tp-tab-signup');
  if (tabSignup) tabSignup.addEventListener('click', () => showTenantTab('signup'));

  const tabForgot = document.getElementById('tp-tab-forgot');
  if (tabForgot) tabForgot.addEventListener('click', () => showTenantTab('forgot'));

  // Links inside panels
  const linkForgot = document.getElementById('link-login-forgot');
  if (linkForgot) linkForgot.addEventListener('click', () => showTenantTab('forgot'));

  const linkSignupLogin = document.getElementById('link-signup-login');
  if (linkSignupLogin) linkSignupLogin.addEventListener('click', () => showTenantTab('login'));

  const linkForgotLogin = document.getElementById('link-forgot-login');
  if (linkForgotLogin) linkForgotLogin.addEventListener('click', () => showTenantTab('login'));

  // Forms
  const loginForm = document.getElementById('tenant-login-form');
  if (loginForm) loginForm.addEventListener('submit', handleTenantLogin);

  const signupForm = document.getElementById('tenant-signup-form');
  if (signupForm) signupForm.addEventListener('submit', handleTenantSignup);

  const forgotForm = document.getElementById('tenant-forgot-form');
  if (forgotForm) forgotForm.addEventListener('submit', handleForgotPwd);

  const paymentForm = document.getElementById('tenant-payment-form');
  if (paymentForm) paymentForm.addEventListener('submit', handlePaymentSubmit);
  document.getElementById('profile-form')?.addEventListener('submit', saveProfile);
  document.getElementById('maintenance-form')?.addEventListener('submit', submitMaintenance);
  document.querySelectorAll('.privacy-request').forEach(btn => btn.addEventListener('click', () => submitPrivacyRequest(btn.dataset.request)));
  document.getElementById('download-lease')?.addEventListener('click', () => window.showToast('Your lease document will be uploaded by your landlord. Contact your property manager if you need a copy.', 'info'));

  // Buttons
  const btnPendingSignout = document.getElementById('btn-pending-signout');
  if (btnPendingSignout) btnPendingSignout.addEventListener('click', showPendingSignOut);

  const btnDashboardSignout = document.getElementById('btn-dashboard-signout');
  if (btnDashboardSignout) {
    btnDashboardSignout.addEventListener('click', () => {
      window.logout ? window.logout() : localStorage.clear();
    });
  }

  // Password strength checker
  const signupPass = document.getElementById('tp-signup-pass');
  if (signupPass) {
    signupPass.addEventListener('input', (e) => {
      updatePwdStrength(e.target.value, 'tp-pwd-bar', 'tp-pwd-label');
    });
  }

  window.renderNavbar('tenant');
  const user = window.getCurrentUser();
  if (user && user.role === 'tenant') {
    if (user.is_approved === false) {
      showPendingApproval(user);
    } else {
      showTenantDashboard(user);
    }
  }
});

function showTenantTab(tab) {
  ['login','signup','forgot'].forEach(t => {
    const panel = document.getElementById('tp-panel-' + t);
    const btn = document.getElementById('tp-tab-' + t);
    if (panel) panel.style.display = t === tab ? 'block' : 'none';
    if (btn) {
      btn.style.color = t === tab ? 'var(--accent-clay)' : 'var(--fg-ink)';
      btn.style.opacity = t === tab ? '1' : '0.5';
      btn.style.borderBottom = t === tab ? '2px solid var(--accent-clay)' : '2px solid transparent';
    }
  });
}

function updatePwdStrength(value, barId, labelId) {
  const result = window.checkPasswordStrength ? window.checkPasswordStrength(value) : { level: 'weak', label: '' };
  const bar = document.getElementById(barId);
  const lbl = document.getElementById(labelId);
  if (bar) bar.className = 'pwd-strength-bar ' + result.level;
  if (lbl) lbl.textContent = result.label;
}

async function handleTenantLogin(e) {
  e.preventDefault();
  const email = document.getElementById('tp-login-email').value.trim();
  const pass = document.getElementById('tp-login-pass').value;
  const errBox = document.getElementById('tp-login-error');
  if (errBox) { errBox.textContent = ''; errBox.style.display = 'none'; }

  try {
    const res = await window.apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password: pass, expected_role: 'tenant' }),
      skipGlobalToast: true
    });
    if (res.user.role !== 'tenant') {
      const msg = 'This portal is for tenants only. Staff use the Staff Portal.';
      if (errBox) { errBox.textContent = msg; errBox.style.display = 'block'; }
      else { window.showToast(msg, 'error'); }
      return;
    }
    window.setCurrentUser(res.user);
    window.showToast(`Welcome, ${res.user.full_name}!`, 'success');
    showTenantDashboard(res.user);
  } catch (err) {
    if (err.message && err.message.toLowerCase().includes('pending approval')) {
      showPendingApproval(null);
      return;
    }
    const msg = err.message || 'Invalid email or password.';
    if (errBox) {
      errBox.textContent = msg;
      errBox.style.display = 'block';
    } else {
      window.showToast(msg, 'error');
    }
  }
}

async function handleTenantSignup(e) {
  e.preventDefault();
  const fullName = document.getElementById('tp-signup-name').value.trim();
  const email = document.getElementById('tp-signup-email').value.trim();
  const phone = document.getElementById('tp-signup-phone').value.trim();
  const password = document.getElementById('tp-signup-pass').value;
  const strength = window.checkPasswordStrength ? window.checkPasswordStrength(password) : { level: 'weak' };
  if (strength.level === 'weak') {
    window.showToast('Password must be at least 8 characters with letters and numbers.', 'error');
    return;
  }
  if (!document.getElementById('tp-signup-consent').checked) return window.showToast('Please agree to the Terms of Service and Privacy Policy.', 'error');
  const btn = document.querySelector('#tenant-signup-form button[type="submit"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Creating accountâ€¦'; }
  try {
    const res = await window.apiRequest('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ full_name: fullName, email, phone_number: phone, password, role: 'tenant' })
    });
    window.setCurrentUser(res.user);
    showPendingApproval(res.user);
  } catch (err) {
    const msg = (err && err.message) ? err.message : 'Sign up failed. Please try again.';
    window.showToast(msg, 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'Create Account'; }
  }
}

async function handleForgotPwd(e) {
  e.preventDefault();
  const email = document.getElementById('tp-forgot-email').value.trim();
  try {
    await window.apiRequest('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email })
    });
    window.showToast('Password reset link sent! Check your email inbox.', 'success');
    setTimeout(() => showTenantTab('login'), 2500);
  } catch (err) {}
}

function showPendingApproval(user) {
  const authSect = document.getElementById('tenant-auth-section');
  const dashSect = document.getElementById('tenant-dashboard-section');
  const pendSect = document.getElementById('tenant-pending-section');
  
  if (authSect) authSect.style.display = 'none';
  if (dashSect) dashSect.style.display = 'none';
  if (pendSect) pendSect.style.display = 'block';
  
  const nameLine = document.getElementById('pending-name-line');
  if (nameLine && user) {
    nameLine.textContent = `Hi, ${user.full_name || 'there'}! Your account is under review.`;
  }
}

function showPendingSignOut() {
  window.logout ? window.logout() : localStorage.clear();
  const pendSect = document.getElementById('tenant-pending-section');
  const authSect = document.getElementById('tenant-auth-section');
  if (pendSect) pendSect.style.display = 'none';
  if (authSect) authSect.style.display = 'block';
  showTenantTab('login');
}

function showTenantDashboard(user) {
  const authSect = document.getElementById('tenant-auth-section');
  const pendSect = document.getElementById('tenant-pending-section');
  const dashSect = document.getElementById('tenant-dashboard-section');
  
  if (authSect) authSect.style.display = 'none';
  if (pendSect) pendSect.style.display = 'none';
  if (dashSect) dashSect.style.display = 'block';

  const greeting = document.getElementById('td-greeting');
  if (greeting) greeting.textContent = `Hello, ${user.full_name || 'Tenant'}`;
  
  const account = document.getElementById('td-account');
  if (account) account.textContent = `Account: ${user.account_number || 'Ã¢â‚¬â€'}  Ã¢â‚¬Â¢  ${user.email}`;
  
  const unit = document.getElementById('td-unit');
  if (unit) unit.textContent = user.unit_id ? `Unit ${user.unit_id}` : 'Ã¢â‚¬â€';
  
  const accno = document.getElementById('td-accno');
  if (accno) accno.textContent = user.account_number || 'Ã¢â‚¬â€';

  const rent = document.getElementById('td-rent');
  if (rent && user.monthly_rent) {
    rent.textContent = `KES ${Number(user.monthly_rent).toLocaleString()}`;
  }
  
  const balance = document.getElementById('td-balance');
  if (balance) balance.textContent = 'CalculatingÃ¢â‚¬Â¦';

  loadTenantPayments(user);
  loadTenantProfile();
  loadMaintenance();
  loadAnnouncements();
}

async function loadTenantPayments(user) {
  try {
    const res = await window.apiRequest('/payments/me');
    const allPmts = res.payments || [];
    const mine = allPmts.filter(p => p.tenant_id === user.id);

    const loadingEl = document.getElementById('td-payments-loading');
    const tableEl = document.getElementById('td-payments-table');
    const noPmts = document.getElementById('td-no-payments');
    const tbody = document.getElementById('td-payments-body');
    if (loadingEl) loadingEl.style.display = 'none';

    if (!mine.length) {
      if (noPmts) noPmts.style.display = 'block';
      const balanceEl = document.getElementById('td-balance');
      if (balanceEl) balanceEl.textContent = 'KES 0';
      return;
    }

    if (tableEl) tableEl.style.display = 'table';
    if (tbody) {
      tbody.innerHTML = '';
      let totalPaid = 0;
      mine.slice().reverse().forEach(p => {
        const statusColor = p.status === 'approved' ? '#4aae72' : p.status === 'rejected' ? '#e85d4a' : '#e8a94a';
        const statusLabel = (p.status || 'pending').charAt(0).toUpperCase() + (p.status || 'pending').slice(1);
        if (p.status === 'approved') totalPaid += Number(p.amount_paid || p.amount || 0);
        tbody.innerHTML += `
          <tr style="border-bottom:1px solid var(--border-warm);">
            <td style="padding:0.65rem 0.25rem;font-family:monospace;font-size:0.75rem;color:var(--fg-ink);">${p.mpesa_code || 'Ã¢â‚¬â€'}</td>
            <td style="padding:0.65rem 0.25rem;text-align:right;font-family:var(--font-serif);font-size:0.85rem;color:var(--fg-ink);">KES ${Number(p.amount_paid || p.amount || 0).toLocaleString()} <button class="receipt-btn" data-payment='${encodeURIComponent(JSON.stringify(p))}' type="button">Print</button></td>
            <td style="padding:0.65rem 0.25rem;text-align:center;">
              <span style="padding:0.2rem 0.65rem;border-radius:9999px;font-size:0.65rem;font-weight:700;background:${statusColor}20;color:${statusColor};">${statusLabel}</span>
            </td>
            <td style="padding:0.65rem 0.25rem;text-align:right;font-size:0.7rem;color:var(--fg-ink);opacity:0.5;">${p.payment_date ? new Date(p.payment_date).toLocaleDateString('en-KE') : 'Ã¢â‚¬â€'}</td>
          </tr>`;
      });
      tbody.querySelectorAll('.receipt-btn').forEach(btn => btn.addEventListener('click', () => downloadReceipt(JSON.parse(decodeURIComponent(btn.dataset.payment)))));

      const monthlyRent = Number(user.monthly_rent || 0);
      const balanceVal = monthlyRent - totalPaid;
      const balanceEl = document.getElementById('td-balance');
      if (balanceEl) {
        balanceEl.textContent =
          balanceVal > 0 ? `KES ${balanceVal.toLocaleString()} due` :
          balanceVal < 0 ? `KES ${Math.abs(balanceVal).toLocaleString()} credit` : 'Paid Ã¢Å“â€œ';
        balanceEl.style.color = balanceVal > 0 ? 'var(--accent-clay)' : '#4aae72';
      }
    }

  } catch (err) {
    const loadingEl = document.getElementById('td-payments-loading');
    if (loadingEl) loadingEl.textContent = 'Could not load payment history.';
  }
}

async function handlePaymentSubmit(e) {
  e.preventDefault();
  const user = window.getCurrentUser();
  if (!user) return window.showToast('Please sign in first.', 'error');

  const mpesa_code = document.getElementById('tp-mpesa-code').value.trim().toUpperCase();
  const amount = parseFloat(document.getElementById('tp-pay-amount').value);
  const note = document.getElementById('tp-pay-note').value.trim();

  const btn = e.currentTarget.querySelector('button[type="submit"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Submitting…'; }
  try {
    await window.apiRequest('/payments', {
      method: 'POST',
      body: JSON.stringify({
        amount,
        mpesa_code,
        payment_date: new Date().toISOString().split('T')[0],
        notes: note,
        status: 'pending'
      })
    });
    window.showToast('Payment submitted! Awaiting approval from your landlord.', 'success');
    document.getElementById('tp-mpesa-code').value = '';
    document.getElementById('tp-pay-amount').value = '';
    document.getElementById('tp-pay-note').value = '';
    loadTenantPayments(user);
  } catch (err) { if (btn) { btn.disabled = false; btn.textContent = 'Submit Payment for Approval'; } window.showToast(err.message || 'Payment could not be submitted.', 'error'); }
}

async function loadTenantProfile() {
  try {
    const { tenant } = await window.apiRequest('/tenants/me');
    ['name','phone','emergency-contact','emergency-phone'].forEach(key => { const el = document.getElementById(`profile-${key}`); if (el) el.value = tenant[{name:'full_name',phone:'phone_number','emergency-contact':'emergency_contact','emergency-phone':'emergency_phone'}[key]] || ''; });
    document.getElementById('profile-email').textContent = `${tenant.email} ${tenant.email_verified ? '✅ Verified' : '⚠️ Unverified'}`;
    document.getElementById('support-phone').textContent = tenant.support_contact?.phone || 'See your welcome email';
    document.getElementById('support-email').textContent = tenant.support_contact?.email || '';
    document.getElementById('emergency-phone').textContent = tenant.support_contact?.phone || 'See your welcome email';
    document.getElementById('lease-details').innerHTML = `Lease: ${tenant.lease_start_date || '—'} to ${tenant.lease_end_date || '—'}<br>Monthly rent: KES ${Number(tenant.monthly_rent || 0).toLocaleString()}<br>Deposit: KES ${Number(tenant.deposit_amount || 0).toLocaleString()} (${tenant.deposit_returned ? 'Returned' : 'Held'})`;
  } catch (_) {}
}
async function saveProfile(e) { e.preventDefault(); try { await window.apiRequest('/tenants/me', {method:'PUT',body:JSON.stringify({full_name:document.getElementById('profile-name').value,phone_number:document.getElementById('profile-phone').value,emergency_contact:document.getElementById('profile-emergency-contact').value,emergency_phone:document.getElementById('profile-emergency-phone').value})}); window.showToast('Profile updated.', 'success'); } catch(e) { window.showToast(e.message || 'Could not save profile.', 'error'); } }
async function loadMaintenance() { try { const res=await window.apiRequest('/maintenance'); document.getElementById('maintenance-list').innerHTML=(res.requests||[]).map(x=>`<p><strong>${x.title || x.category}</strong> — ${(x.status||'pending').replace('_',' ')} </p>`).join('') || 'No maintenance requests yet.'; } catch (_) {} }
async function submitMaintenance(e) { e.preventDefault(); try { await window.apiRequest('/maintenance',{method:'POST',body:JSON.stringify({category:document.getElementById('maintenance-category').value,description:document.getElementById('maintenance-description').value,urgency:document.getElementById('maintenance-urgency').value})}); e.currentTarget.reset(); window.showToast('Maintenance request submitted.', 'success'); loadMaintenance(); } catch(e) { window.showToast(e.message || 'Could not submit request.', 'error'); } }
async function loadAnnouncements() { try { const res=await window.apiRequest('/announcements'); document.getElementById('announcements-list').innerHTML=(res.announcements||[]).slice(0,5).map(x=>`<article style="border-left:4px solid ${String(x.title).toLowerCase().includes('urgent') ? '#c0392b' : '#e8a94a'};padding:.6rem;margin:.5rem 0"><strong>${x.title}</strong><br>${x.body}</article>`).join('') || 'No current notices.'; } catch (_) {} }
async function submitPrivacyRequest(request_type) { try { await window.apiRequest('/privacy-requests',{method:'POST',body:JSON.stringify({request_type})}); window.showToast('Your privacy request has been recorded.', 'success'); } catch(e) { window.showToast(e.message || 'Could not submit request.', 'error'); } }
function downloadReceipt(payment) { const user=window.getCurrentUser()||{}; const receipt=window.open('', '_blank'); receipt.document.write(`<html><head><title>Payment Receipt</title><style>body{font:16px Arial;padding:32px}h1{color:#276749}@media print{button{display:none}}</style></head><body><h1>Payment Receipt</h1><p><b>Tenant:</b> ${user.full_name||''}<br><b>Account:</b> ${user.account_number||''}<br><b>M-Pesa code:</b> ${payment.mpesa_code||''}<br><b>Amount:</b> KES ${Number(payment.amount_paid||payment.amount||0).toLocaleString()}<br><b>Date:</b> ${payment.payment_date||''}<br><b>Status:</b> ${payment.status||'pending'}</p><button onclick="window.print()">Print</button></body></html>`); receipt.document.close(); }
