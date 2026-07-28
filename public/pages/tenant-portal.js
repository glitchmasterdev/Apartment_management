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
  try {
    const res = await window.apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password: pass, expected_role: 'tenant' })
    });
    if (res.user.role !== 'tenant') {
      window.showToast('This portal is for tenants only. Staff use the Staff Portal.', 'error');
      return;
    }
    window.setCurrentUser(res.user, res.token);
    window.showToast(`Welcome, ${res.user.full_name}!`, 'success');
    showTenantDashboard(res.user);
  } catch (err) {
    if (err.message && err.message.toLowerCase().includes('pending approval')) {
      showPendingApproval(null);
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
  const btn = document.querySelector('#tenant-signup-form button[type="submit"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Creating account�'; }
  try {
    const res = await window.apiRequest('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ full_name: fullName, email, phone_number: phone, password, role: 'tenant' })
    });
    window.setCurrentUser(res.user, res.token);
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
  if (account) account.textContent = `Account: ${user.account_number || '—'}  •  ${user.email}`;
  
  const unit = document.getElementById('td-unit');
  if (unit) unit.textContent = user.unit_id ? `Unit ${user.unit_id}` : '—';
  
  const accno = document.getElementById('td-accno');
  if (accno) accno.textContent = user.account_number || '—';

  const rent = document.getElementById('td-rent');
  if (rent && user.monthly_rent) {
    rent.textContent = `KES ${Number(user.monthly_rent).toLocaleString()}`;
  }
  
  const balance = document.getElementById('td-balance');
  if (balance) balance.textContent = 'Calculating…';

  loadTenantPayments(user);
}

async function loadTenantPayments(user) {
  try {
    const res = await window.apiRequest('/payments');
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
        if (p.status === 'approved') totalPaid += Number(p.amount || 0);
        tbody.innerHTML += `
          <tr style="border-bottom:1px solid var(--border-warm);">
            <td style="padding:0.65rem 0.25rem;font-family:monospace;font-size:0.75rem;color:var(--fg-ink);">${p.mpesa_code || '—'}</td>
            <td style="padding:0.65rem 0.25rem;text-align:right;font-family:var(--font-serif);font-size:0.85rem;color:var(--fg-ink);">KES ${Number(p.amount || 0).toLocaleString()}</td>
            <td style="padding:0.65rem 0.25rem;text-align:center;">
              <span style="padding:0.2rem 0.65rem;border-radius:9999px;font-size:0.65rem;font-weight:700;background:${statusColor}20;color:${statusColor};">${statusLabel}</span>
            </td>
            <td style="padding:0.65rem 0.25rem;text-align:right;font-size:0.7rem;color:var(--fg-ink);opacity:0.5;">${p.payment_date ? new Date(p.payment_date).toLocaleDateString('en-KE') : '—'}</td>
          </tr>`;
      });

      const monthlyRent = Number(user.monthly_rent || 0);
      const balanceVal = monthlyRent - totalPaid;
      const balanceEl = document.getElementById('td-balance');
      if (balanceEl) {
        balanceEl.textContent =
          balanceVal > 0 ? `KES ${balanceVal.toLocaleString()} due` :
          balanceVal < 0 ? `KES ${Math.abs(balanceVal).toLocaleString()} credit` : 'Paid ✓';
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

  try {
    await window.apiRequest('/payments', {
      method: 'POST',
      body: JSON.stringify({
        tenant_id: user.id,
        unit_id: user.unit_id,
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
  } catch (err) {}
}
