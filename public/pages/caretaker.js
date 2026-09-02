let caretakerUnits = [];

document.addEventListener('DOMContentLoaded', async () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Setup change listener for building select
  const bldgSelect = document.getElementById('caretaker-bldg-select');
  if (bldgSelect) {
    bldgSelect.addEventListener('change', (e) => {
      window.setBuildingFilter(e.target.value);
      loadCaretakerUnits();
    });
  }

  // Setup bulk presence listeners
  const btnBulkPresent = document.getElementById('btn-bulk-present');
  if (btnBulkPresent) {
    btnBulkPresent.addEventListener('click', () => handleBulkPresence('present'));
  }
  const btnBulkAbsent = document.getElementById('btn-bulk-absent');
  if (btnBulkAbsent) {
    btnBulkAbsent.addEventListener('click', () => handleBulkPresence('absent'));
  }

  // Setup search keyup listener
  const searchInput = document.getElementById('caretaker-search');
  if (searchInput) {
    searchInput.addEventListener('keyup', renderCaretakerUnits);
  }

  // Setup move out form submit
  const moveOutForm = document.getElementById('move-out-form');
  if (moveOutForm) {
    moveOutForm.addEventListener('submit', handleMoveOutSubmit);
  }

  // Setup cancel button in sign out modal
  const btnCancelSignout = document.getElementById('btn-cancel-move-out');
  if (btnCancelSignout) {
    btnCancelSignout.addEventListener('click', closeSignOutModal);
  }

  // Event delegation for dynamically generated presence/signout buttons
  const container = document.getElementById('caretaker-units-list');
  if (container) {
    container.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn) return;
      
      const action = btn.dataset.action;
      const unitId = btn.dataset.unitId;
      
      if (action === 'presence') {
        markPresence(unitId, 'present');
      } else if (action === 'signout') {
        const tenantId = btn.dataset.tenantId;
        const unitNo = btn.dataset.unitNumber;
        openSignOutModal(unitId, tenantId, unitNo);
      }
    });
  }

  window.ThemeManager && window.ThemeManager.init();
  loadCaretakerMaintenance();
  window.PWAManager && window.PWAManager.init();
  if (!window.requireRole(['caretaker'])) return;
  await window.renderNavbar('caretaker');
  await loadCaretakerUnits();
  window.addEventListener('buildingChanged', loadCaretakerUnits);
});

async function loadCaretakerMaintenance() {
  const list = document.getElementById('caretaker-maintenance-list');
  if (!list) return;
  try {
    const res = await window.apiRequest('/maintenance');
    const requests = (res.requests || []).filter(r => r.status !== 'resolved' && r.status !== 'closed');
    list.innerHTML = requests.length ? requests.slice(0, 5).map(r => `<div class="py-2 border-b border-white/10"><strong>${r.title || r.category || 'Request'}</strong><br><span class="opacity-70">${r.urgency || 'Routine'} · ${r.status || 'open'}</span></div>`).join('') : 'No open maintenance requests.';
  } catch (_) { list.textContent = 'Could not load maintenance requests.'; }
}

async function loadCaretakerUnits() {
  const bldgId = window.getBuildingFilter() || 'bldg-001';
  const bldgSelect = document.getElementById('caretaker-bldg-select');
  if (bldgSelect) bldgSelect.value = bldgId;

  try {
    const res = await window.apiRequest(`/units?building_id=${bldgId}`);
    caretakerUnits = res.units || [];
  } catch (e) {
    caretakerUnits = [];
  }

  // Update stats
  const statTotal = document.getElementById('stat-total');
  if (statTotal) statTotal.innerText = caretakerUnits.length;

  const statOccupied = document.getElementById('stat-occupied');
  if (statOccupied) statOccupied.innerText = caretakerUnits.filter(u => u.status === 'occupied').length;

  const statVacant = document.getElementById('stat-vacant');
  if (statVacant) statVacant.innerText = caretakerUnits.filter(u => u.status === 'vacant').length;

  renderCaretakerUnits();
}

function renderCaretakerUnits() {
  const searchInput = document.getElementById('caretaker-search');
  const search = searchInput ? searchInput.value.toLowerCase() : '';
  const container = document.getElementById('caretaker-units-list');
  if (!container) return;
  container.innerHTML = '';

  const filtered = caretakerUnits.filter(u => {
    const name = u.tenant ? u.tenant.full_name.toLowerCase() : '';
    return u.unit_number.toLowerCase().includes(search) || name.includes(search);
  });

  if (!filtered.length) {
    container.innerHTML = `<div class="text-center py-10 text-[oklch(0.5_0.012_60)] text-sm">No units found.</div>`;
    return;
  }

  filtered.forEach(u => {
    const isOccupied = u.status === 'occupied';
    const tenant = u.tenant;

    const statusDot = isOccupied
      ? `<span class="w-2.5 h-2.5 rounded-full bg-emerald-400 flex-shrink-0"></span>`
      : u.status === 'maintenance'
        ? `<span class="w-2.5 h-2.5 rounded-full bg-amber-400 flex-shrink-0"></span>`
        : `<span class="w-2.5 h-2.5 rounded-full bg-[oklch(0.4_0.012_60)] flex-shrink-0"></span>`;

    container.innerHTML += `
      <div class="ct-card p-5">
        <div class="flex items-start justify-between mb-4">
          <div class="flex items-center gap-3">
            ${statusDot}
            <div>
              <span class="font-serif text-xl font-medium text-[#fbf9f4]">Unit ${u.unit_number}</span>
              <span class="block text-[10px] uppercase tracking-widest mt-0.5" style="color: oklch(0.55 0.012 60);">Floor ${u.floor || 1}</span>
            </div>
          </div>
          <span class="text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${
            isOccupied
              ? 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/30'
              : 'bg-[oklch(0.28_0.015_60)] text-[oklch(0.6_0.012_60)]'
          }">
            ${u.status.toUpperCase()}
          </span>
        </div>

        ${tenant ? `
          <div class="p-3 rounded-xl mb-4" style="background: oklch(0.18 0.015 58);">
            <span class="ct-micro block mb-1">Resident</span>
            <span class="font-medium text-sm text-[#c2593f]">${tenant.full_name}</span>
            <span class="block text-xs mt-0.5" style="color: oklch(0.55 0.012 60);">${tenant.phone_number}</span>
          </div>
        ` : `
          <div class="p-3 rounded-xl mb-4 text-center" style="background: oklch(0.18 0.015 58);">
            <span class="text-xs" style="color: oklch(0.5 0.012 60);">No tenant assigned</span>
          </div>
        `}

        <div class="grid grid-cols-2 gap-2">
          ${isOccupied ? `
            <button data-action="presence" data-unit-id="${u.id}"
              class="py-2.5 rounded-xl text-xs font-bold transition"
              style="background: rgba(215,101,69,0.15); color: #f2b08d; border: 1px solid rgba(215,101,69,0.35);">
              ✓ Present Today
            </button>
            <button data-action="signout" data-unit-id="${u.id}" data-tenant-id="${tenant ? tenant.id : ''}" data-unit-number="${u.unit_number}"
              class="py-2.5 rounded-xl text-xs font-bold transition"
              style="background: rgba(220,38,38,0.12); color: #fca5a5; border: 1px solid rgba(220,38,38,0.2);">
               Sign Out
            </button>
          ` : `
            <a href="units.html"
              class="col-span-2 text-center py-2.5 rounded-xl text-xs font-bold transition"
              style="background: oklch(0.28 0.015 60); color: oklch(0.7 0.012 60);">
              + Onboard Tenant via Portal
            </a>
          `}
        </div>
      </div>`;
  });
}

async function handleBulkPresence(action) {
  const bldgId = window.getBuildingFilter() || 'bldg-001';
  try {
    const res = await window.apiRequest('/occupancy/daily-presence/bulk', {
      method: 'POST',
      body: JSON.stringify({ building_id: bldgId, action })
    });
    window.showToast(res.message, 'success');
  } catch (err) {}
}

function openSignOutModal(unitId, tenantId, unitNo) {
  const modal = document.getElementById('modal-signout');
  const idInput = document.getElementById('signout-unit-id');
  const tenantInput = document.getElementById('signout-tenant-id');
  const label = document.getElementById('signout-unit-label');
  
  if (idInput) idInput.value = unitId;
  if (tenantInput) tenantInput.value = tenantId;
  if (label) label.innerText = `Unit #${unitNo}`;
  if (modal) modal.classList.replace('hidden', 'flex');
}

function closeSignOutModal() {
  const modal = document.getElementById('modal-signout');
  if (modal) modal.classList.replace('flex', 'hidden');
}

async function handleMoveOutSubmit(e) {
  e.preventDefault();
  const payload = {
    unit_id: document.getElementById('signout-unit-id').value,
    tenant_id: document.getElementById('signout-tenant-id').value,
    notes: document.getElementById('signout-notes').value
  };
  try {
    const res = await window.apiRequest('/occupancy/sign-out', {
      method: 'POST', body: JSON.stringify(payload)
    });
    window.showToast(res.message, 'success');
    closeSignOutModal();
    await loadCaretakerUnits();
  } catch (err) {}
}

async function markPresence(unitId, status) {
  try {
    const res = await window.apiRequest('/occupancy/daily-presence', {
      method: 'POST',
      body: JSON.stringify({ unit_id: unitId, status })
    });
    window.showToast(res.message, 'success');
  } catch (err) {}
}
