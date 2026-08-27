/* Global Vanilla JavaScript Module - Nairobi Editorial Rental Platform */
window.API_URL = window.API_URL || '/api';

/* ─── Theme Management (Dark / Light Mode) ─── */
window.ThemeManager = {
  init() {
    const saved = localStorage.getItem('nrb_theme') || 'light';
    this.apply(saved);
    if (typeof window.ensureThemeToggle === 'function') window.ensureThemeToggle();
  },
  apply(theme) {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('nrb_theme', theme);
    const floatingToggle = document.getElementById('floating-theme-toggle');
    if (floatingToggle) floatingToggle.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
  },
  toggle() {
    const isDark = document.documentElement.classList.contains('dark');
    this.apply(isDark ? 'light' : 'dark');
    // Update toggle buttons
    document.querySelectorAll('[data-theme-icon]').forEach(el => {
      el.textContent = isDark ? '🌙' : '☀️';
    });
  },
  getCurrent() {
    return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
  }
};

// This control is deliberately independent of the navigation renderer, so
// theme switching remains available on every authenticated view.
window.ensureThemeToggle = function() {
  if (document.getElementById('floating-theme-toggle')) return;
  const button = document.createElement('button');
  button.id = 'floating-theme-toggle';
  button.type = 'button';
  button.textContent = window.ThemeManager.getCurrent() === 'dark' ? 'Light mode' : 'Dark mode';
  button.setAttribute('aria-label', 'Toggle colour theme');
  button.style.cssText = 'position:fixed;right:1rem;bottom:1rem;z-index:1000;border:1px solid var(--border-warm);border-radius:999px;padding:.55rem .85rem;background:var(--card-bg);color:var(--fg-ink);font-size:.72rem;font-weight:700;cursor:pointer;box-shadow:var(--shadow-warm);';
  button.addEventListener('click', () => window.ThemeManager.toggle());
  document.body.appendChild(button);
};

// Apply theme immediately on load (before DOM renders to prevent flash)
(function() {
  const saved = localStorage.getItem('nrb_theme') || 'light';
  if (saved === 'dark') document.documentElement.classList.add('dark');
})();

/* ─── PWA Service Worker & Install Prompt ─── */
let _pwaInstallEvent = null;

window.PWAManager = {
  init() {
    // Register service worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').then(reg => {
        console.log('[PWA] Service worker registered:', reg.scope);
      }).catch(err => console.warn('[PWA] SW registration failed:', err));
    }
    // Capture install prompt
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      _pwaInstallEvent = e;
      this.showBanner();
    });
    window.addEventListener('appinstalled', () => {
      this.hideBanner();
      window.showToast('App installed successfully! 🎉', 'success');
    });
  },
  showBanner() {
    const banner = document.getElementById('pwa-install-banner');
    if (banner) banner.classList.add('visible');
  },
  hideBanner() {
    const banner = document.getElementById('pwa-install-banner');
    if (banner) banner.classList.remove('visible');
  },
  async install() {
    if (!_pwaInstallEvent) {
      window.showToast('App already installed or not available on this browser.', 'info');
      return;
    }
    _pwaInstallEvent.prompt();
    const { outcome } = await _pwaInstallEvent.userChoice;
    if (outcome === 'accepted') {
      window.showToast('Installing Apartment Management…', 'success');
    }
    _pwaInstallEvent = null;
    this.hideBanner();
  }
};

/* ─── Session & Auth ─── */
window.getCurrentUser = function() {
  const sessionStr = localStorage.getItem('nrb_session');
  if (!sessionStr) return null;
  try { return JSON.parse(sessionStr); } catch { return null; }
};

window.setCurrentUser = function(userData) {
  // Store non-sensitive user profile in localStorage for UI state, while auth token is strictly stored in HttpOnly cookie
  localStorage.setItem('nrb_session', JSON.stringify(userData));
};

window.logout = async function() {
  try {
    await window.apiRequest('/auth/logout', { method: 'POST', skipGlobalToast: true });
  } catch (err) {
    console.warn('Logout request failed:', err);
  }
  localStorage.removeItem('nrb_session');
  localStorage.removeItem('selectedBuildingId');
  window.location.href = 'index.html';
};

/* ─── Role Access Control ─── */
// requireRole(allowedRoles): call at top of each protected page
window.requireRole = function(allowedRoles = []) {
  const user = window.getCurrentUser();
  if (!user) {
    window.showToast('Please log in to access this page.', 'error');
    setTimeout(() => { window.location.href = 'index.html'; }, 1200);
    return false;
  }
  if (!allowedRoles.includes(user.role)) {
    const roleLabels = { landlord: 'Landlord', caretaker: 'Caretaker', tenant: 'Tenant' };
    window.showToast(`Access denied. This page is for ${allowedRoles.map(r => roleLabels[r] || r).join(' & ')} only.`, 'error');
    setTimeout(() => {
      if (user.role === 'tenant') { window.location.href = 'tenant-portal.html'; }
      else if (user.role === 'caretaker') { window.location.href = 'payments.html'; }
      else { window.location.href = 'dashboard.html'; }
    }, 1500);
    return false;
  }
  return true;
};

/* ─── Building Filter ─── */
window.getBuildingFilter = function() {
  return localStorage.getItem('selectedBuildingId') || '';
};
window.setBuildingFilter = function(bldgId) {
  if (bldgId) localStorage.setItem('selectedBuildingId', bldgId);
  else localStorage.removeItem('selectedBuildingId');
  window.dispatchEvent(new Event('buildingChanged'));
};

/* ─── CSRF Token Helper ─── */
function getCsrfToken() {
  // Reads the csrf_token cookie set by the server on every page load.
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/* ─── API Request Wrapper ─── */
window.apiRequest = async function(endpoint, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const session = window.getCurrentUser();

  // Real backend request
  const url = `${window.API_URL}${endpoint}`;
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
  }

  try {
  } catch (err) {
    console.warn('Logout request failed:', err);
  }
  localStorage.removeItem('nrb_session');
  localStorage.removeItem('selectedBuildingId');
  window.location.href = 'index.html';
};

/* ─── Role Access Control ─── */
// requireRole(allowedRoles): call at top of each protected page
window.requireRole = function(allowedRoles = []) {
  const user = window.getCurrentUser();
  if (!user) {
    window.showToast('Please log in to access this page.', 'error');
    setTimeout(() => { window.location.href = 'index.html'; }, 1200);
    return false;
  }
  if (!allowedRoles.includes(user.role)) {
    const roleLabels = { landlord: 'Landlord', caretaker: 'Caretaker', tenant: 'Tenant' };
    window.showToast(`Access denied. This page is for ${allowedRoles.map(r => roleLabels[r] || r).join(' & ')} only.`, 'error');
    setTimeout(() => {
      if (user.role === 'tenant') { window.location.href = 'tenant-portal.html'; }
      else if (user.role === 'caretaker') { window.location.href = 'payments.html'; }
      else { window.location.href = 'dashboard.html'; }
    }, 1500);
    return false;
  }
  return true;
};

/* ─── Building Filter ─── */
window.getBuildingFilter = function() {
  return localStorage.getItem('selectedBuildingId') || '';
};
window.setBuildingFilter = function(bldgId) {
  if (bldgId) localStorage.setItem('selectedBuildingId', bldgId);
  else localStorage.removeItem('selectedBuildingId');
  window.dispatchEvent(new Event('buildingChanged'));
};

/* ─── CSRF Token Helper ─── */
function getCsrfToken() {
  // Reads the csrf_token cookie set by the server on every page load.
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/* ─── API Request Wrapper ─── */
window.apiRequest = async function(endpoint, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const session = window.getCurrentUser();

  // Real backend request
  const url = `${window.API_URL}${endpoint}`;
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
  }

  try {
    const response = await fetch(url, { ...options, method, credentials: 'include', headers });

    // Safely parse JSON — the server may return a plain-text error (e.g. Vercel
    // gateway errors like "Internal Server Error") which would crash JSON.parse.
    let data = {};
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      data = await response.json();
    } else {
      const text = await response.text();
      // Attempt to parse anyway in case content-type header is missing
      try { data = JSON.parse(text); } catch { data = { detail: text || response.statusText }; }
    }

    if (!response.ok) {
      const msg = data.detail || data.message || `Request failed (${response.status})`;
      throw new Error(msg);
    }
    return data;
  } catch (error) {
    console.error(`[API Error ${endpoint}]:`, error);
    if (!options.skipGlobalToast) {
      window.showToast(error.message, 'error');
    }
    throw error;
  }
};

/* ─── Toast Notifications ─── */
window.showToast = function(message, type = 'success') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = 'position:fixed;top:1.25rem;left:50%;transform:translateX(-50%);z-index:99999;display:flex;flex-direction:column;align-items:center;gap:0.5rem;pointer-events:none;min-width:280px;max-width:90vw;';
    document.body.appendChild(container);
  }

  const colorMap = {
    success: { bg: '#2d6a4f', dot: '#52b788', text: '#d8f3dc', border: 'rgba(82,183,136,0.4)' },
    error:   { bg: '#7b1d1d', dot: '#f87171', text: '#fee2e2', border: 'rgba(248,113,113,0.4)' },
    info:    { bg: '#1e3a5f', dot: '#60a5fa', text: '#dbeafe', border: 'rgba(96,165,250,0.4)' },
  };
  const c = colorMap[type] || colorMap.success;

  const toast = document.createElement('div');
  toast.style.cssText = `
    display:flex;align-items:center;gap:0.75rem;padding:0.85rem 1.5rem;
    border-radius:0.75rem;font-size:0.9rem;font-weight:600;
    background:${c.bg};color:${c.text};border:1px solid ${c.border};
    box-shadow:0 8px 24px rgba(0,0,0,0.35);transition:all 0.3s ease;
    animation:slideToastDown 0.35s cubic-bezier(0.16,1,0.3,1);
    pointer-events:all;width:100%;max-width:420px;
  `;
  toast.innerHTML = `
    <span style="width:10px;height:10px;border-radius:50%;background:${c.dot};flex-shrink:0;"></span>
    <span style="color:${c.text};flex:1;">${message}</span>
  `;

  if (!document.getElementById('toast-keyframes')) {
    const s = document.createElement('style');
    s.id = 'toast-keyframes';
    s.textContent = `@keyframes slideToastDown{from{opacity:0;transform:translateY(-16px)}to{opacity:1;transform:translateY(0)}}`;
    document.head.appendChild(s);
  }

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(-12px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
};

/* ─── Navbar Renderer ─── */
window.renderNavbar = async function(activePage) {
  const user = window.getCurrentUser();
  const navContainer = document.getElementById('app-navbar');
  if (!navContainer) return;

  let buildings = [];
  const canViewBuildings = user && ['landlord', 'caretaker'].includes(user.role);
  if (canViewBuildings) {
    try {
      const res = await window.apiRequest('/buildings');
      buildings = res.buildings || [];
    } catch (e) {
      // Keep the staff navigation usable when the property list is unavailable.
      buildings = [];
    }
  }

  const currentBldg = window.getBuildingFilter();
  const role = user ? user.role : null;
  const isLandlord = role === 'landlord';
  const isCaretaker = role === 'caretaker';
  const isTenant = role === 'tenant';

  const navLink = (href, page, label) => {
    const active = activePage === page;
    return `<a href="${href}" class="nav-link ${active ? 'nav-link-active' : ''}">${label}</a>`;
  };

  const isDark = window.ThemeManager.getCurrent() === 'dark';

  navContainer.innerHTML = `
    <nav style="background:var(--nav-bg);backdrop-filter:blur(20px);border-bottom:1px solid var(--border-warm);padding:1rem 1.5rem;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:1rem;position:sticky;top:0;z-index:40;">
      <!-- Wordmark -->
      <a href="index.html" style="text-decoration:none;display:flex;align-items:center;gap:0.5rem;">
        <span style="font-family:var(--font-serif);font-size:1.4rem;font-weight:700;color:var(--fg-ink);letter-spacing:-0.02em;">
          Apartment Management<span style="color:var(--accent-clay)">.</span>
        </span>
      </a>

      <!-- Nav Links (role-aware) -->
      <div style="display:flex;align-items:center;gap:1.5rem;font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;color:var(--fg-ink);flex-wrap:wrap;">
        ${navLink('index.html', 'home', 'Overview')}
        ${navLink('units.html', 'units', 'Residences')}
        ${(isLandlord || isCaretaker) ? navLink('dashboard.html', 'dashboard', 'Dashboard') : ''}
        ${(isLandlord || isCaretaker) ? navLink('payments.html', 'payments', 'Approvals') : ''}
        ${isLandlord ? navLink('expenses.html', 'expenses', 'Expenses') : ''}
        ${isLandlord ? navLink('reports.html', 'reports', 'Reports') : ''}
        ${isTenant ? navLink('tenant-portal.html', 'tenant', 'My Portal') : ''}
      </div>

      <!-- Right Controls -->
      <div style="display:flex;align-items:center;gap:0.75rem;">
        <!-- Building filter (staff only) -->
        ${(isLandlord || isCaretaker) ? `
          <select id="nav-building-filter"
            style="background:var(--input-bg);border:1px solid var(--border-warm);color:var(--fg-ink);font-size:0.75rem;font-weight:600;border-radius:999px;padding:0.35rem 1rem;outline:none;cursor:pointer;">
            <option value="">All Buildings</option>
            ${buildings.map(b => `<option value="${b.id}" ${currentBldg === b.id ? 'selected' : ''}>${b.name}</option>`).join('')}
          </select>
        ` : ''}

        <!-- Theme Toggle -->
        <button id="theme-toggle-btn"
          title="Toggle Dark / Light Mode"
          style="background:var(--bg-muted);border:1px solid var(--border-warm);border-radius:999px;padding:0.4rem 0.75rem;cursor:pointer;font-size:0.85rem;color:var(--fg-ink);display:flex;align-items:center;gap:0.35rem;transition:all 0.2s;">
          <span data-theme-icon>${isDark ? '☀️' : '🌙'}</span>
        </button>

        <!-- PWA Install -->
        <button id="nav-install-btn" title="Install as Mobile App"
          style="display:none;background:var(--accent-clay);color:#fff;border:none;border-radius:999px;padding:0.4rem 0.85rem;font-size:0.7rem;font-weight:700;cursor:pointer;letter-spacing:0.05em;">
          📲 Install App
        </button>

        <!-- User / Auth -->
        ${user ? `
          <div style="display:flex;align-items:center;gap:0.5rem;">
            <span class="role-badge role-badge-${role}" style="display:none;display:inline-flex" id="nav-role-badge">${role}</span>
            <span style="font-size:0.75rem;font-weight:500;color:var(--fg-ink);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${user.full_name || user.email}</span>
            <button id="nav-sign-out" style="padding:0.4rem 0.85rem;border-radius:999px;font-size:0.7rem;font-weight:700;background:var(--fg-ink);color:var(--bg-cream);border:none;cursor:pointer;transition:all 0.2s;">Sign Out</button>
          </div>
        ` : `
          <a href="index.html" style="display:inline-flex;align-items:center;padding:0.5rem 1rem;background:var(--accent-clay);color:#fff;border-radius:999px;font-size:0.75rem;font-weight:700;text-decoration:none;">Login</a>
        `}
      </div>
    </nav>

    <!-- PWA Install Banner -->
    <div id="pwa-install-banner" style="display:none;position:fixed;bottom:1.5rem;left:50%;transform:translateX(-50%);z-index:9999;background:var(--card-bg);border:1px solid var(--border-warm);border-radius:var(--radius-card);box-shadow:var(--shadow-hover);padding:1rem 1.5rem;align-items:center;gap:1rem;min-width:300px;max-width:90vw;">
      <div>
        <p style="font-size:0.875rem;font-weight:700;color:var(--fg-ink);margin:0;">Install Apartment Management</p>
        <p style="font-size:0.75rem;color:var(--fg-ink);opacity:0.6;margin:0.25rem 0 0;">Add to your home screen for quick access</p>
      </div>
      <div style="display:flex;gap:0.5rem;margin-left:auto;">
        <button id="pwa-install-confirm" class="btn-terracotta" style="padding:0.5rem 1rem;font-size:0.75rem;">Install</button>
        <button id="pwa-install-later" class="btn-outline-editorial" style="padding:0.5rem 0.75rem;font-size:0.75rem;">Later</button>
      </div>
    </div>
  `;

  // Inline event attributes are blocked by the production Content Security
  // Policy. Bind this listener after rendering so a building change updates
  // shared state and every page subscribed to `buildingChanged` refreshes.
  const buildingFilter = document.getElementById('nav-building-filter');
  if (buildingFilter) {
    buildingFilter.addEventListener('change', (event) => {
      window.setBuildingFilter(event.target.value);
    });
  }
  const themeToggle = document.getElementById('theme-toggle-btn');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      window.ThemeManager.toggle();
      const icon = themeToggle.querySelector('[data-theme-icon]');
      if (icon) icon.textContent = document.documentElement.classList.contains('dark') ? '☀️' : '🌙';
    });
  }
  document.getElementById('nav-install-btn')?.addEventListener('click', () => window.PWAManager.install());
  document.getElementById('nav-sign-out')?.addEventListener('click', () => window.logout());
  document.getElementById('pwa-install-confirm')?.addEventListener('click', () => window.PWAManager.install());
  document.getElementById('pwa-install-later')?.addEventListener('click', () => window.PWAManager.hideBanner());

  // Inject nav link styles
  if (!document.getElementById('nav-link-styles')) {
    const s = document.createElement('style');
    s.id = 'nav-link-styles';
    s.textContent = `
      .nav-link{color:var(--fg-ink);text-decoration:none;opacity:0.78;transition:all 0.2s;padding-bottom:2px;}
      .nav-link:hover{opacity:1;color:var(--hover-fg);background:var(--hover-bg);border-radius:0.35rem;}
      .nav-link-active{opacity:1;color:var(--accent-clay);border-bottom:2px solid var(--accent-clay);}
    `;
    document.head.appendChild(s);
  }

  // Show PWA install button in nav if deferred prompt exists
  window.addEventListener('beforeinstallprompt', () => {
    const btn = document.getElementById('nav-install-btn');
    if (btn) btn.style.display = 'inline-flex';
  });
};

/* ─── Password Strength Helper ─── */
window.checkPasswordStrength = function(password) {
  const hasLength = password.length >= 8;
  const hasLetter = /[A-Za-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);

  if (!hasLength || (!hasLetter && !hasNumber)) return { level: 'weak', label: 'Weak – too short', score: 0 };
  if (hasLength && hasLetter && hasNumber && hasSpecial) return { level: 'strong', label: 'Strong', score: 3 };
  if (hasLength && hasLetter && hasNumber) return { level: 'medium', label: 'Good', score: 2 };
  return { level: 'weak', label: 'Weak – add letters and numbers', score: 1 };
};

/* ─── App Init (called on page load) ─── */
window.initApp = function(activePage, allowedRoles) {
  // Theme
  window.ThemeManager.init();
  window.ensureThemeToggle();
  // PWA
  window.PWAManager.init();
  // Navbar
  window.renderNavbar(activePage);
  // Role guard
  if (allowedRoles && allowedRoles.length > 0) {
    window.requireRole(allowedRoles);
  }
};
