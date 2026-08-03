let rawUnitsData = [];
let currentFilter = 'all';

document.addEventListener('DOMContentLoaded', async () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Setup click listeners for filter buttons
  const btnAll = document.getElementById('btn-status-all');
  if (btnAll) btnAll.addEventListener('click', () => filterStatus('all'));

  const btnOccupied = document.getElementById('btn-status-occupied');
  if (btnOccupied) btnOccupied.addEventListener('click', () => filterStatus('occupied'));

  const btnVacant = document.getElementById('btn-status-vacant');
  if (btnVacant) btnVacant.addEventListener('click', () => filterStatus('vacant'));

  const btnMaint = document.getElementById('btn-status-maintenance');
  if (btnMaint) btnMaint.addEventListener('click', () => filterStatus('maintenance'));

  // Setup keyup listener for search input
  const searchInput = document.getElementById('search-units');
  if (searchInput) {
    searchInput.addEventListener('keyup', renderUnitsTable);
  }

  window.ThemeManager && window.ThemeManager.init();
  window.PWAManager && window.PWAManager.init();
  const user = window.getCurrentUser && window.getCurrentUser();
  const isStaff = user && ['landlord', 'caretaker'].includes(user.role);
  if (!isStaff) {
    currentFilter = 'vacant';
    document.getElementById('btn-status-all').textContent = 'Available Units';
    ['occupied', 'maintenance'].forEach(status => document.getElementById(`btn-status-${status}`)?.classList.add('hidden'));
  }
  await window.renderNavbar('units');
  await loadUnits();
  window.addEventListener('buildingChanged', loadUnits);
});

async function loadUnits() {
  const bldgId = window.getBuildingFilter();
  const user = window.getCurrentUser && window.getCurrentUser();
  const endpoint = user && ['landlord', 'caretaker'].includes(user.role) ? '/units' : '/units/public';
  try {
    const res = await window.apiRequest(`${endpoint}?building_id=${bldgId}`);
    rawUnitsData = res.units || [];
    renderUnitsTable();
  } catch (err) {
    console.error(err);
  }
}

function filterStatus(status) {
  currentFilter = status;
  ['all', 'occupied', 'vacant', 'maintenance'].forEach(st => {
    const btn = document.getElementById(`btn-status-${st}`);
    if (btn) {
      if (st === status) {
        btn.className = "px-4 py-1.5 rounded-full text-xs font-semibold bg-[#1c1a17] text-[#fbf9f4]";
      } else {
        btn.className = "px-4 py-1.5 rounded-full text-xs font-semibold bg-[#ede9df] text-[#1c1a17]/70 hover:text-[#1c1a17]";
      }
    }
  });
  renderUnitsTable();
}

function renderUnitsTable() {
  const searchEl = document.getElementById('search-units');
  const search = searchEl ? searchEl.value.toLowerCase() : '';
  const tbody = document.getElementById('units-table-body');
  if (!tbody) return;
  tbody.innerHTML = '';

  const filtered = rawUnitsData.filter(u => {
    const matchesFilter = currentFilter === 'all' || u.status === currentFilter;
    const matchesSearch = u.unit_number.toLowerCase().includes(search);
    return matchesFilter && matchesSearch;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="py-6 text-center text-[#1c1a17]/40">No units found matching criteria.</td></tr>`;
    return;
  }

  filtered.forEach(u => {
    const tenant = u.tenant;
    const statusBadge = u.status === 'occupied' 
      ? '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">Occupied</span>'
      : u.status === 'vacant'
      ? '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-[#ede9df] text-[#1c1a17]/70 font-semibold">Vacant / Available</span>'
      : '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-100 text-amber-900 font-semibold">Maintenance</span>';

    const occupancyText = u.status === 'occupied'
      ? tenant
        ? `<div class="space-y-1"><div><span class="text-emerald-700 font-semibold">${escapeHtml(tenant.full_name || 'Assigned tenant')}</span><br><span class="text-xs text-[#1c1a17]/60">${escapeHtml(tenant.email || 'No email')}</span></div><div class="flex gap-2"><button type="button" data-action="move-out" data-tenant-id="${tenant.id}" class="text-xs text-[#c2593f] font-semibold hover:underline">Move out</button><button type="button" data-action="delete-tenant" data-tenant-id="${tenant.id}" data-tenant-name="${escapeHtml(tenant.full_name || 'this tenant')}" class="text-xs text-red-700 font-semibold hover:underline">Delete data</button></div></div>`
        : '<span class="text-emerald-700 font-semibold">Occupied (tenant record unavailable)</span>'
      : u.status === 'vacant'
      ? '<span class="text-[#c2593f] font-semibold">Available for booking</span>'
      : '<span class="text-amber-700 font-semibold">Temporarily unavailable</span>';

    const deleteUnitAction = u.status === 'vacant'
      ? `<button type="button" data-action="delete-unit" data-unit-id="${u.id}" data-unit-number="${escapeHtml(u.unit_number)}" class="text-xs text-red-700 font-semibold hover:underline">Delete unit</button>`
      : '';

    tbody.innerHTML += `
      <tr class="hover:bg-[#ede9df]/30 transition">
        <td class="py-3.5 font-serif font-semibold text-[#1c1a17] numeral-serif text-sm">Unit ${u.unit_number}</td>
        <td class="py-3.5 text-[#1c1a17]/60">${escapeHtml(u.building_name || 'Unknown building')}</td>
        <td class="py-3.5 text-[#1c1a17]/60">Floor ${u.floor || 1}</td>
        <td class="py-3.5 font-serif font-medium text-[#1c1a17] numeral-serif">KES ${u.rent_amount.toLocaleString()}</td>
        <td class="py-3.5">${statusBadge}</td>
        <td class="py-3.5">${occupancyText}${deleteUnitAction ? `<div class="mt-1">${deleteUnitAction}</div>` : ''}</td>
      </tr>
    `;
  });
}

function escapeHtml(value) {
  const node = document.createElement('div');
  node.textContent = String(value || '');
  return node.innerHTML;
}

document.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const tenantId = button.dataset.tenantId;
  const unitId = button.dataset.unitId;

  if (button.dataset.action === 'move-out') {
    if (!tenantId) return;
    if (!confirm('Mark this tenant as moved out and return the unit to vacant? Their historical record will be kept.')) return;
    try {
      const result = await window.apiRequest(`/tenants/${tenantId}/move-out`, { method: 'POST' });
      window.showToast(result.message || 'Tenant moved out.', 'success');
      await loadUnits();
    } catch (error) {
      window.showToast(error.message || 'Could not move out tenant.', 'error');
    }
  }

  if (button.dataset.action === 'delete-tenant') {
    if (!tenantId) return;
    const name = button.dataset.tenantName || 'this tenant';
    if (!confirm(`Permanently delete ${name}'s tenant data and related history? This cannot be undone.`)) return;
    try {
      await window.apiRequest(`/tenants/${tenantId}`, { method: 'DELETE' });
      window.showToast('Tenant data deleted.', 'success');
      await loadUnits();
    } catch (error) {
      window.showToast(error.message || 'Could not delete tenant data.', 'error');
    }
  }

  if (button.dataset.action === 'delete-unit') {
    const unitNumber = button.dataset.unitNumber || 'this unit';
    if (!unitId || !confirm(`Permanently delete vacant unit ${unitNumber}? This cannot be undone.`)) return;
    try {
      const result = await window.apiRequest(`/units/${unitId}`, { method: 'DELETE' });
      window.showToast(result.message || 'Vacant unit deleted.', 'success');
      await loadUnits();
    } catch (error) {
      window.showToast(error.message || 'Could not delete unit.', 'error');
    }
  }
});
