/* Global Vanilla JavaScript Module - Nairobi Editorial Rental Platform */
window.API_URL = window.API_URL || '/api';

/* ─── Theme Management (Dark / Light Mode) ─── */
window.ThemeManager = {
  init() {
    const saved = localStorage.getItem('nrb_theme') || 'light';
    this.apply(saved);
  },
  apply(theme) {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('nrb_theme', theme);
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

window.setCurrentUser = function(userData, token) {
  // Store user profile in localStorage for UI state, while auth token is handled in HttpOnly cookie
  localStorage.setItem('nrb_session', JSON.stringify({ ...userData, token }));
};

window.logout = async function() {
  try {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
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

  // ── Client-Side Isolated Demo Mode Interceptor ──
  if (window.DemoStore && window.DemoStore.isDemoSession()) {
    const storeData = window.DemoStore.get();

    // 1. GET /buildings
    if (endpoint.startsWith('/buildings') && method === 'GET') {
      return { buildings: storeData.buildings };
    }
    // POST /buildings
    if (endpoint === '/buildings' && method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const newBldg = {
        id: `demo-bldg-${Date.now()}`,
        name: body.name || 'New Demo Building',
        location: body.location || 'Nairobi, Kenya',
        total_floors: parseInt(body.total_floors) || 1,
        is_demo: true
      };
      storeData.buildings.push(newBldg);
      window.DemoStore.save(storeData);
      return { status: 'success', building: newBldg };
    }

    // 2. GET /units
    if (endpoint.startsWith('/units') && method === 'GET') {
      let filtered = [...storeData.units];
      if (endpoint.includes('building_id=')) {
        const bId = new URLSearchParams(endpoint.split('?')[1]).get('building_id');
        if (bId) filtered = filtered.filter(u => u.building_id === bId);
      }
      return { units: filtered };
    }
    // POST /units
    if (endpoint === '/units' && method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const newUnit = {
        id: `demo-u-${Date.now()}`,
        building_id: body.building_id,
        unit_number: body.unit_number,
        floor: parseInt(body.floor) || 1,
        rent_amount: parseFloat(body.rent_amount) || 15000,
        deposit_amount: parseFloat(body.rent_amount) || 15000,
        deposit_paid: false,
        status: 'vacant',
        is_active: true,
        is_demo: true
      };
      storeData.units.push(newUnit);
      window.DemoStore.save(storeData);
      return { status: 'success', unit: newUnit };
    }

    // 2.5. GET /auth/pending-tenants
    if (endpoint.startsWith('/auth/pending-tenants')) {
      return { tenants: [] };
    }

    // 3. GET /tenants
    if (endpoint.startsWith('/tenants') && method === 'GET') {
      let filtered = [...storeData.tenants];
      if (endpoint.includes('building_id=')) {
        const bId = new URLSearchParams(endpoint.split('?')[1]).get('building_id');
        if (bId) {
          const bUnitIds = storeData.units.filter(u => u.building_id === bId).map(u => u.id);
          filtered = filtered.filter(t => bUnitIds.includes(t.unit_id));
        }
      }
      // Attach details
      const result = filtered.map(t => {
        const u = storeData.units.find(unit => unit.id === t.unit_id) || {};
        const b = storeData.buildings.find(bldg => bldg.id === u.building_id) || {};
        const tPayments = storeData.payments.filter(p => p.tenant_id === t.id);
        const totalPaid = tPayments.filter(p => p.status === 'approved').reduce((sum, p) => sum + (p.amount_paid || 0), 0);
        const monthlyRent = t.monthly_rent || 0;
        const balance = Math.max(0, monthlyRent - totalPaid);
        return {
          ...t,
          unit_number: u.unit_number || 'N/A',
          building_name: b.name || 'N/A',
          ledger: {
            monthly_rent: monthlyRent,
            total_paid: totalPaid,
            balance: balance,
            is_in_arrears: balance > 0,
            status_label: balance > 0 ? `In Arrears (KES ${balance.toLocaleString()})` : 'Fully Paid'
          }
        };
      });
      return { tenants: result };
    }
    // POST /tenants (assign/create)
    if (endpoint === '/tenants' && method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const newTenant = {
        id: `demo-t-${Date.now()}`,
        unit_id: body.unit_id,
        full_name: body.full_name,
        phone_number: body.phone_number || '',
        email: body.email || '',
        account_number: `NRB-DEMO-${Math.floor(100 + Math.random() * 900)}`,
        monthly_rent: parseFloat(body.monthly_rent) || 15000,
        lease_start_date: body.lease_start_date || new Date().toISOString().split('T')[0],
        is_active: true,
        is_approved: true,
        is_demo: true
      };
      // Mark unit as occupied
      const targetUnit = storeData.units.find(u => u.id === body.unit_id);
      if (targetUnit) targetUnit.status = 'occupied';

      storeData.tenants.push(newTenant);
      window.DemoStore.save(storeData);
      return { status: 'success', tenant: newTenant };
    }
    // DELETE /tenants/all
    if (endpoint === '/tenants/all' && method === 'DELETE') {
      const count = storeData.tenants.length;
      storeData.tenants = [];
      storeData.units.forEach(u => u.status = 'vacant');
      window.DemoStore.save(storeData);
      return { status: 'success', message: `Removed all ${count} tenants.` };
    }
    // DELETE /tenants/:id
    if (endpoint.startsWith('/tenants/') && method === 'DELETE') {
      const tId = endpoint.split('/')[2];
      const idx = storeData.tenants.findIndex(t => t.id === tId);
      if (idx !== -1) {
        const t = storeData.tenants[idx];
        const u = storeData.units.find(unit => unit.id === t.unit_id);
        if (u) u.status = 'vacant';
        storeData.tenants.splice(idx, 1);
        window.DemoStore.save(storeData);
      }
      return { status: 'success', message: 'Tenant removed successfully' };
    }

    // 4. GET /payments
    if (endpoint.startsWith('/payments') && method === 'GET') {
      return { payments: storeData.payments };
    }
    // GET /payments/pending
    if (endpoint.startsWith('/payments/pending') && method === 'GET') {
      const pending = storeData.payments.filter(p => p.status === 'pending').map(p => {
        const u = storeData.units.find(unit => unit.id === p.unit_id) || {};
        const t = storeData.tenants.find(ten => ten.id === p.tenant_id) || {};
        return {
          ...p,
          unit_number: u.unit_number || 'N/A',
          tenant_name: t.full_name || 'N/A',
          phone_number: t.phone_number || 'N/A'
        };
      });
      return { pending_payments: pending };
    }
    // POST /payments/approve
    if (endpoint === '/payments/approve' && method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const pIds = body.payment_ids || [];
      let count = 0;
      storeData.payments.forEach(p => {
        if (pIds.includes(p.id)) {
          p.status = 'approved';
          count++;
        }
      });
      window.DemoStore.save(storeData);
      return { status: 'success', approved_count: count };
    }
    // POST /payments/reject
    if (endpoint === '/payments/reject' && method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const pIds = body.payment_ids || [];
      let count = 0;
      storeData.payments.forEach(p => {
        if (pIds.includes(p.id)) {
          p.status = 'rejected';
          p.rejection_reason = body.reason || 'Rejected in demo mode';
          count++;
        }
      });
      window.DemoStore.save(storeData);
      return { status: 'success', rejected_count: count };
    }
    // POST /payments
    if (endpoint === '/payments' && method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const newPayment = {
        id: `p-demo-${Date.now()}`,
        tenant_id: body.tenant_id,
        unit_id: body.unit_id,
        amount_paid: parseFloat(body.amount) || 0,
        payment_date: body.payment_date || new Date().toISOString(),
        mpesa_code: body.mpesa_code || `DEMO${Date.now()}`,
        tenant_message: body.notes || '',
        status: 'pending',
        is_demo: true
      };
      storeData.payments.push(newPayment);
      window.DemoStore.save(storeData);
      return { status: 'success', message: 'Payment submitted for approval.', payment: newPayment };
    }

    // 5. GET /expenses
    if (endpoint.startsWith('/expenses') && method === 'GET') {
      const result = storeData.expenses.map(e => {
        const b = storeData.buildings.find(bldg => bldg.id === e.building_id) || {};
        return { ...e, building_name: b.name || 'N/A' };
      });
      return { expenses: result };
    }
    // POST /expenses
    if (endpoint === '/expenses' && method === 'POST') {
      const body = JSON.parse(options.body || '{}');
      const newExp = {
        id: `exp-demo-${Date.now()}`,
        building_id: body.building_id,
        category: body.category,
        amount: parseFloat(body.amount) || 0,
        date: body.date || new Date().toISOString().split('T')[0],
        description: body.description || '',
        is_demo: true
      };
      storeData.expenses.push(newExp);
      window.DemoStore.save(storeData);
      return { status: 'success', expense: newExp };
    }

    // 6. GET /reports/occupancy
    if (endpoint.startsWith('/reports/occupancy') && method === 'GET') {
      const totalUnits = storeData.units.length || 1;
      const occupiedUnits = storeData.units.filter(u => u.status === 'occupied').length;
      const rate = Math.round((occupiedUnits / totalUnits) * 100);
      return {
        occupancy_rate: rate,
        total_units: totalUnits,
        occupied_units: occupiedUnits,
        vacant_units: totalUnits - occupiedUnits,
        trend: [
          { month: 'Jan', rate: 70 }, { month: 'Feb', rate: 75 },
          { month: 'Mar', rate: 80 }, { month: 'Apr', rate: 82 },
          { month: 'May', rate: 85 }, { month: 'Jun', rate: rate }
        ]
      };
    }

    // 7. POST /demo/reset
    if (endpoint === '/demo/reset' && method === 'POST') {
      window.DemoStore.reset();
      return { status: 'success', message: 'Demo data reset successfully for this device!' };
    }
  }

  // Real backend fallback for non-demo users or endpoints
  const url = `${window.API_URL}${endpoint}`;
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };

  if (session && session.token) headers['Authorization'] = `Bearer ${session.token}`;

  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
  }

  try {
    const response = await fetch(url, { ...options, method, credentials: 'include', headers });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.message || 'API request failed');
    return data;
  } catch (error) {
    console.error(`[API Error ${endpoint}]:`, error);
    window.showToast(error.message, 'error');
    throw error;
  }
};

/* ─── Toast Notifications ─── */
window.showToast = function(message, type = 'success') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;z-index:99999;display:flex;flex-direction:column;gap:0.5rem;';
    document.body.appendChild(container);
  }

  const colorMap = {
    success: { dot: '#4aae72', text: '#a8f0c0', border: 'rgba(74,174,114,0.2)' },
    error:   { dot: '#e85d4a', text: '#ffb3aa', border: 'rgba(232,93,74,0.2)' },
    info:    { dot: '#82aaee', text: '#c0d4ff', border: 'rgba(130,170,238,0.2)' },
  };
  const c = colorMap[type] || colorMap.success;

  const toast = document.createElement('div');
  toast.style.cssText = `
    display:flex;align-items:center;gap:0.75rem;padding:0.75rem 1.25rem;
    border-radius:999px;font-size:0.8125rem;font-weight:600;
    background:var(--card-bg);color:${c.text};border:1px solid ${c.border};
    box-shadow:var(--shadow-hover);transition:all 0.3s ease;
    animation:slideToast 0.3s cubic-bezier(0.16,1,0.3,1);
  `;
  toast.innerHTML = `
    <span style="width:8px;height:8px;border-radius:50%;background:${c.dot};flex-shrink:0;"></span>
    <span style="color:var(--fg-ink)">${message}</span>
  `;

  if (!document.getElementById('toast-keyframes')) {
    const s = document.createElement('style');
    s.id = 'toast-keyframes';
    s.textContent = `@keyframes slideToast{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}`;
    document.head.appendChild(s);
  }

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
};

/* ─── Navbar Renderer ─── */
window.renderNavbar = async function(activePage) {
  const user = window.getCurrentUser();
  const navContainer = document.getElementById('app-navbar');
  if (!navContainer) return;

  let buildings = [];
  try {
    const res = await window.apiRequest('/buildings');
    buildings = res.buildings || [];
  } catch (e) {
    buildings = [
      { id: 'bldg-001', name: 'Kileleshwa Park Heights' },
      { id: 'bldg-002', name: 'Westlands Executive Suites' }
    ];
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
          <select id="nav-building-filter" onchange="window.setBuildingFilter(this.value)"
            style="background:var(--input-bg);border:1px solid var(--border-warm);color:var(--fg-ink);font-size:0.75rem;font-weight:600;border-radius:999px;padding:0.35rem 1rem;outline:none;cursor:pointer;">
            <option value="">All Buildings</option>
            ${buildings.map(b => `<option value="${b.id}" ${currentBldg === b.id ? 'selected' : ''}>${b.name}</option>`).join('')}
          </select>
        ` : ''}

        <!-- Theme Toggle -->
        <button id="theme-toggle-btn" onclick="window.ThemeManager.toggle();this.querySelector('[data-theme-icon]').textContent=document.documentElement.classList.contains('dark')?'☀️':'🌙';"
          title="Toggle Dark / Light Mode"
          style="background:var(--bg-muted);border:1px solid var(--border-warm);border-radius:999px;padding:0.4rem 0.75rem;cursor:pointer;font-size:0.85rem;color:var(--fg-ink);display:flex;align-items:center;gap:0.35rem;transition:all 0.2s;">
          <span data-theme-icon>${isDark ? '☀️' : '🌙'}</span>
        </button>

        <!-- PWA Install -->
        <button id="nav-install-btn" onclick="window.PWAManager.install()" title="Install as Mobile App"
          style="display:none;background:var(--accent-clay);color:#fff;border:none;border-radius:999px;padding:0.4rem 0.85rem;font-size:0.7rem;font-weight:700;cursor:pointer;letter-spacing:0.05em;">
          📲 Install App
        </button>

        <!-- User / Auth -->
        ${user ? `
          <div style="display:flex;align-items:center;gap:0.5rem;">
            <span class="role-badge role-badge-${role}" style="display:none;display:inline-flex" id="nav-role-badge">${role}</span>
            <span style="font-size:0.75rem;font-weight:500;color:var(--fg-ink);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${user.full_name || user.email}</span>
            <button onclick="window.logout()" style="padding:0.4rem 0.85rem;border-radius:999px;font-size:0.7rem;font-weight:700;background:var(--fg-ink);color:var(--bg-cream);border:none;cursor:pointer;transition:all 0.2s;">Sign Out</button>
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
        <button onclick="window.PWAManager.install()" class="btn-terracotta" style="padding:0.5rem 1rem;font-size:0.75rem;">Install</button>
        <button onclick="window.PWAManager.hideBanner()" class="btn-outline-editorial" style="padding:0.5rem 0.75rem;font-size:0.75rem;">Later</button>
      </div>
    </div>
  `;

  // Inject nav link styles
  if (!document.getElementById('nav-link-styles')) {
    const s = document.createElement('style');
    s.id = 'nav-link-styles';
    s.textContent = `
      .nav-link{color:var(--fg-ink);text-decoration:none;opacity:0.6;transition:all 0.2s;padding-bottom:2px;}
      .nav-link:hover{opacity:1;color:var(--accent-clay);}
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
  // PWA
  window.PWAManager.init();
  // Navbar
  window.renderNavbar(activePage);
  // Role guard
  if (allowedRoles && allowedRoles.length > 0) {
    window.requireRole(allowedRoles);
  }
};
