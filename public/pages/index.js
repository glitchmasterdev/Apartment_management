let currentAuthMode = 'landlord';

document.addEventListener('DOMContentLoaded', () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Theme toggle listener
  const btnTheme = document.getElementById('hero-theme-btn');
  if (btnTheme) {
    btnTheme.addEventListener('click', () => {
      if (window.ThemeManager) {
        window.ThemeManager.toggle();
        const iconSpan = btnTheme.querySelector('[data-theme-icon]');
        if (iconSpan) {
          iconSpan.textContent = document.documentElement.classList.contains('dark') ? '☀️' : '🌙';
        }
      }
    });
  }

  // Open modal buttons (Staff / Landlord)
  const staffButtons = ['btn-nav-staff', 'btn-hero-staff', 'btn-hero-signin', 'btn-footer-staff'];
  staffButtons.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener('click', () => openAuthModal('landlord'));
  });

  // Open modal buttons (Tenant)
  const tenantButtons = ['btn-nav-tenant', 'btn-hero-tenant', 'btn-footer-tenant'];
  tenantButtons.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener('click', () => openAuthModal('tenant'));
  });

  // Close modal button
  const btnCloseAuth = document.getElementById('btn-close-auth-modal');
  if (btnCloseAuth) {
    btnCloseAuth.addEventListener('click', closeAuthModal);
  }

  // Auth form submit
  const authForm = document.getElementById('auth-form');
  if (authForm) {
    authForm.addEventListener('submit', handleAuthSubmit);
  }

  // Forgot password modal handlers
  const btnOpenForgotPw = document.getElementById('btn-open-forgot-pw');
  if (btnOpenForgotPw) {
    btnOpenForgotPw.addEventListener('click', () => {
      closeAuthModal();
      openForgotPwModal();
    });
  }

  const btnCloseForgotPw = document.getElementById('btn-close-forgot-pw');
  if (btnCloseForgotPw) {
    btnCloseForgotPw.addEventListener('click', closeForgotPwModal);
  }

  // Close modal when clicking outside (on backdrop) or pressing Escape
  const authModal = document.getElementById('auth-modal');
  if (authModal) {
    authModal.addEventListener('click', (e) => {
      if (e.target === authModal) closeAuthModal();
    });
  }

  const forgotModal = document.getElementById('forgot-pw-modal');
  if (forgotModal) {
    forgotModal.addEventListener('click', (e) => {
      if (e.target === forgotModal) closeForgotPwModal();
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeAuthModal();
      closeForgotPwModal();
    }
  });

  const forgotPwForm = document.getElementById('forgot-pw-form');
  if (forgotPwForm) {
    forgotPwForm.addEventListener('submit', handleForgotPwSubmit);
  }

  // Load custom pricing tier settings from platform settings API
  loadDynamicPricing();
});

function openForgotPwModal() {
  const modal = document.getElementById('forgot-pw-modal');
  const emailInput = document.getElementById('forgot-pw-email');
  const authEmailInput = document.getElementById('auth-email');
  const msgEl = document.getElementById('forgot-pw-message');

  if (msgEl) msgEl.classList.add('hidden');
  if (emailInput && authEmailInput && authEmailInput.value) {
    emailInput.value = authEmailInput.value.trim();
  }

  if (modal) {
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }
}

function closeForgotPwModal() {
  const modal = document.getElementById('forgot-pw-modal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

async function handleForgotPwSubmit(e) {
  e.preventDefault();
  const email = document.getElementById('forgot-pw-email').value.trim();
  const msgEl = document.getElementById('forgot-pw-message');
  const btn = document.getElementById('btn-submit-forgot-pw');

  if (!email) return;

  try {
    btn.textContent = 'Sending…';
    btn.disabled = true;

    const res = await window.apiRequest('/landlord/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email })
    });

    if (msgEl) {
      msgEl.textContent = res.message || 'If the email matches an active account, password reset instructions have been sent.';
      msgEl.className = 'text-xs p-3 rounded-xl bg-green-50 text-green-800 border border-green-200';
      msgEl.classList.remove('hidden');
    }
    window.showToast('Reset instructions sent to registered email!', 'success');

    setTimeout(() => {
      closeForgotPwModal();
      btn.textContent = 'Send Reset Link →';
      btn.disabled = false;
      if (msgEl) msgEl.classList.add('hidden');
    }, 4000);
  } catch (err) {
    btn.textContent = 'Send Reset Link →';
    btn.disabled = false;
    if (msgEl) {
      msgEl.textContent = err.message || 'Failed to send reset link. Try again.';
      msgEl.className = 'text-xs p-3 rounded-xl bg-red-50 text-red-700 border border-red-200';
      msgEl.classList.remove('hidden');
    }
  }
}

async function loadDynamicPricing() {
  try {
    const settings = await window.apiRequest('/settings', { skipGlobalToast: true });
    if (!settings) return;

    if (settings.price_std_title) {
      const stdTitle = document.getElementById('price-std-title');
      if (stdTitle) stdTitle.textContent = settings.price_std_title;
    }
    if (settings.price_std_val) {
      const stdVal = document.getElementById('price-std-val');
      if (stdVal) stdVal.textContent = settings.price_std_val;
    }
    if (settings.price_std_sub) {
      const stdSub = document.getElementById('price-std-sub');
      if (stdSub) stdSub.textContent = settings.price_std_sub;
    }
    if (settings.price_std_features) {
      const stdFeatures = document.getElementById('price-std-features');
      if (stdFeatures) {
        const lines = settings.price_std_features.split('\n').filter(l => l.trim());
        stdFeatures.innerHTML = lines.map(l => `<li>✓ ${l.replace(/^✓\s*/, '')}</li>`).join('');
      }
    }

    if (settings.price_ent_title) {
      const entTitle = document.getElementById('price-ent-title');
      if (entTitle) entTitle.textContent = settings.price_ent_title;
    }
    if (settings.price_ent_val) {
      const entVal = document.getElementById('price-ent-val');
      if (entVal) entVal.textContent = settings.price_ent_val;
    }
    if (settings.price_ent_features) {
      const entFeatures = document.getElementById('price-ent-features');
      if (entFeatures) {
        const lines = settings.price_ent_features.split('\n').filter(l => l.trim());
        entFeatures.innerHTML = lines.map(l => `<li>✓ ${l.replace(/^✓\s*/, '')}</li>`).join('');
      }
    }
  } catch (err) {
    // Graceful fallback to static HTML defaults
  }
}

function openAuthModal(role) {
  currentAuthMode = role;
  const modal = document.getElementById('auth-modal');
  const title = document.getElementById('auth-modal-title');
  const sub = document.getElementById('auth-modal-sub');
  const signupLink = document.getElementById('auth-modal-signup-link');
  const errBox = document.getElementById('auth-error-msg');
  if (errBox) { errBox.textContent = ''; errBox.classList.add('hidden'); }

  if (!modal || !title || !sub) return;

  if (role === 'landlord') {
    title.textContent = 'Staff Portal Sign In';
    sub.textContent = 'Enter landlord or caretaker credentials only.';
    if (signupLink) signupLink.style.display = 'none';
  } else {
    title.textContent = 'Tenant Portal Sign In';
    sub.textContent = 'Access your unit ledger and submit M-Pesa proof.';
    if (signupLink) signupLink.style.display = 'block';
  }

  modal.classList.remove('hidden');
  modal.classList.add('flex');
}

function closeAuthModal() {
  const modal = document.getElementById('auth-modal');
  const errBox = document.getElementById('auth-error-msg');
  const authForm = document.getElementById('auth-form');
  const emailInput = document.getElementById('auth-email');
  const passwordInput = document.getElementById('auth-password');

  if (errBox) { errBox.textContent = ''; errBox.classList.add('hidden'); }
  if (authForm) authForm.reset();
  if (emailInput) emailInput.value = '';
  if (passwordInput) passwordInput.value = '';

  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const email = document.getElementById('auth-email').value;
  const password = document.getElementById('auth-password').value;
  const expected_role = currentAuthMode === 'landlord' ? 'staff' : 'tenant';
  const errBox = document.getElementById('auth-error-msg');
  if (errBox) { errBox.textContent = ''; errBox.classList.add('hidden'); }

  try {
    const res = await window.apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, expected_role }),
      skipGlobalToast: true
    });

    if (res.user) {
      window.setCurrentUser(res.user);
      window.showToast('Login successful!', 'success');
      closeAuthModal();

      setTimeout(() => {
        if (res.user.role === 'tenant') {
          window.location.href = 'tenant-portal.html';
        } else if (res.user.role === 'caretaker') {
          window.location.href = 'payments.html';
        } else {
          window.location.href = 'dashboard.html';
        }
      }, 800);
    }
  } catch (err) {
    const errorText = err.message || 'Invalid email or password.';
    if (errBox) {
      errBox.textContent = errorText;
      errBox.classList.remove('hidden');
    } else {
      window.showToast(errorText, 'error');
    }
  }
}
