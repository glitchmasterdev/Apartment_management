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

  // Load custom pricing tier settings from platform settings API
  loadDynamicPricing();
});

async function loadDynamicPricing() {
  try {
    const settings = await window.apiRequest('/settings');
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
  if (!modal || !title || !sub) return;

  if (role === 'landlord') {
    title.textContent = 'Staff Portal Sign In';
    sub.textContent = 'Enter landlord or caretaker credentials only.';
  } else {
    title.textContent = 'Tenant Portal Sign In';
    sub.textContent = 'Access your unit ledger and submit M-Pesa proof.';
  }

  modal.classList.remove('hidden');
  modal.classList.add('flex');
}

function closeAuthModal() {
  const modal = document.getElementById('auth-modal');
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

  try {
    const res = await window.apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, expected_role })
    });

    if (res.user && res.token) {
      window.setCurrentUser(res.user, res.token);
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
    window.showToast(err.message, 'error');
  }
}
