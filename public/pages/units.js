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
  await window.renderNavbar('units');
  await loadUnits();
  window.addEventListener('buildingChanged', loadUnits);
});

async function loadUnits() {
  const bldgId = window.getBuildingFilter();
  try {
    const res = await window.apiRequest(`/units?building_id=${bldgId}`);
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
    tbody.innerHTML = `<tr><td colspan="5" class="py-6 text-center text-[#1c1a17]/40">No units found matching criteria.</td></tr>`;
    return;
  }

  filtered.forEach(u => {
    const statusBadge = u.status === 'occupied' 
      ? '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">Occupied</span>'
      : u.status === 'vacant'
      ? '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-[#ede9df] text-[#1c1a17]/70 font-semibold">Vacant / Available</span>'
      : '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-100 text-amber-900 font-semibold">Maintenance</span>';

    const occupancyText = u.status === 'occupied' 
      ? '<span class="text-emerald-700 font-semibold">Booked / Occupied</span>'
      : u.status === 'vacant'
      ? '<span class="text-[#c2593f] font-semibold">Available for booking</span>'
      : '<span class="text-amber-700 font-semibold">Temporarily unavailable</span>';

    tbody.innerHTML += `
      <tr class="hover:bg-[#ede9df]/30 transition">
        <td class="py-3.5 font-serif font-semibold text-[#1c1a17] numeral-serif text-sm">Unit ${u.unit_number}</td>
        <td class="py-3.5 text-[#1c1a17]/60">Floor ${u.floor || 1}</td>
        <td class="py-3.5 font-serif font-medium text-[#1c1a17] numeral-serif">KES ${u.rent_amount.toLocaleString()}</td>
        <td class="py-3.5">${statusBadge}</td>
        <td class="py-3.5">${occupancyText}</td>
      </tr>
    `;
  });
}
