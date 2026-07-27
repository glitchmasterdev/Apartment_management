let yoyChartInstance = null;

document.addEventListener('DOMContentLoaded', async () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Setup click listeners for header buttons
  const btnOpenChangePw = document.getElementById('btn-open-change-pw');
  if (btnOpenChangePw) btnOpenChangePw.addEventListener('click', openChangePwModal);

  const btnOpenSettings = document.getElementById('btn-open-settings');
  if (btnOpenSettings) btnOpenSettings.addEventListener('click', openSettingsModal);

  const btnOpenAddBldg = document.getElementById('btn-open-add-building');
  if (btnOpenAddBldg) btnOpenAddBldg.addEventListener('click', openAddBuildingModal);

  const btnOpenEditBldg = document.getElementById('btn-open-edit-building');
  if (btnOpenEditBldg) btnOpenEditBldg.addEventListener('click', openEditBuildingModal);

  const btnOpenAddUnit = document.getElementById('btn-open-add-unit');
  if (btnOpenAddUnit) btnOpenAddUnit.addEventListener('click', openAddUnitModal);

  const btnOpenBulk = document.getElementById('btn-open-bulk-import');
  if (btnOpenBulk) btnOpenBulk.addEventListener('click', openBulkImportModal);

  // Modal Cancel / Close click listeners
  const btnCloseChangePw = document.getElementById('btn-close-change-pw');
  if (btnCloseChangePw) btnCloseChangePw.addEventListener('click', closeChangePwModal);
  const btnCancelChangePw = document.getElementById('btn-cancel-change-pw');
  if (btnCancelChangePw) btnCancelChangePw.addEventListener('click', closeChangePwModal);

  const btnCloseSettings = document.getElementById('btn-close-settings');
  if (btnCloseSettings) btnCloseSettings.addEventListener('click', closeSettingsModal);
  const btnCancelSettings = document.getElementById('btn-cancel-settings');
  if (btnCancelSettings) btnCancelSettings.addEventListener('click', closeSettingsModal);

  const btnCloseAddBldg = document.getElementById('btn-close-add-building');
  if (btnCloseAddBldg) btnCloseAddBldg.addEventListener('click', closeAddBuildingModal);
  const btnCancelAddBldg = document.getElementById('btn-cancel-add-building');
  if (btnCancelAddBldg) btnCancelAddBldg.addEventListener('click', closeAddBuildingModal);

  const btnCloseEditBldg = document.getElementById('btn-close-edit-building');
  if (btnCloseEditBldg) btnCloseEditBldg.addEventListener('click', closeEditBuildingModal);
  const btnCancelEditBldg = document.getElementById('btn-cancel-edit-building');
  if (btnCancelEditBldg) btnCancelEditBldg.addEventListener('click', closeEditBuildingModal);

  const btnCloseAddUnit = document.getElementById('btn-close-add-unit');
  if (btnCloseAddUnit) btnCloseAddUnit.addEventListener('click', closeAddUnitModal);
  const btnCancelAddUnit = document.getElementById('btn-cancel-add-unit');
  if (btnCancelAddUnit) btnCancelAddUnit.addEventListener('click', closeAddUnitModal);

  const btnCloseBulk = document.getElementById('btn-close-bulk-import');
  if (btnCloseBulk) btnCloseBulk.addEventListener('click', closeBulkImportModal);
  const btnCancelBulk = document.getElementById('btn-cancel-bulk-import');
  if (btnCancelBulk) btnCancelBulk.addEventListener('click', closeBulkImportModal);

  // Form submits
  const changePwForm = document.getElementById('change-pw-form');
  if (changePwForm) changePwForm.addEventListener('submit', submitChangePw);

  const settingsForm = document.getElementById('settings-form');
  if (settingsForm) settingsForm.addEventListener('submit', handleSaveSettings);

  const addBuildingForm = document.getElementById('add-building-form');
  if (addBuildingForm) addBuildingForm.addEventListener('submit', handleAddBuilding);

  const editBuildingForm = document.getElementById('edit-building-form');
  if (editBuildingForm) editBuildingForm.addEventListener('submit', handleEditBuilding);

  const addUnitForm = document.getElementById('add-unit-form');
  if (addUnitForm) addUnitForm.addEventListener('submit', handleAddUnit);

  const bulkImportForm = document.getElementById('bulk-import-form');
  if (bulkImportForm) bulkImportForm.addEventListener('submit', handleBulkImport);

  // Password toggles
  const btnToggleCpCurrent = document.getElementById('btn-toggle-cp-current');
  if (btnToggleCpCurrent) {
    btnToggleCpCurrent.addEventListener('click', () => togglePasswordVisibility('cp-current', btnToggleCpCurrent));
  }
  const btnToggleCpNew = document.getElementById('btn-toggle-cp-new');
  if (btnToggleCpNew) {
    btnToggleCpNew.addEventListener('click', () => togglePasswordVisibility('cp-new', btnToggleCpNew));
  }
  const btnToggleCpConfirm = document.getElementById('btn-toggle-cp-confirm');
  if (btnToggleCpConfirm) {
    btnToggleCpConfirm.addEventListener('click', () => togglePasswordVisibility('cp-confirm', btnToggleCpConfirm));
  }

  window.ThemeManager && window.ThemeManager.init();
  window.PWAManager && window.PWAManager.init();
  if (!window.requireRole(['landlord'])) return;
  await window.renderNavbar('dashboard');
  await loadDashboardData();
  window.addEventListener('buildingChanged', loadDashboardData);
});

async function loadDashboardData() {
  const bldgId = window.getBuildingFilter();
  
  try {
    const kpiRes = await window.apiRequest(`/reports/dashboard?building_id=${bldgId}`);
    const kpis = kpiRes.kpis || {};
    document.getElementById('kpi-total-units').innerText = kpis.total_units || 0;
    document.getElementById('kpi-occupied-units').innerText = kpis.occupied_units || 0;
    document.getElementById('kpi-occupancy-rate').innerText = `${kpis.occupancy_rate || 0}%`;
    document.getElementById('kpi-monthly-revenue').innerText = `KES ${(kpis.monthly_revenue || 0).toLocaleString()}`;

    // Populate Top Arrears
    const arrearsBody = document.getElementById('arrears-table-body');
    if (arrearsBody) {
      arrearsBody.innerHTML = '';
      const arrearsList = kpiRes.top_arrears || [];
      if (arrearsList.length === 0) {
        arrearsBody.innerHTML = `<tr><td colspan="2" class="py-4 text-center text-[#1c1a17]/40">All tenants are fully paid up! 🎉</td></tr>`;
      } else {
        arrearsList.forEach(item => {
          arrearsBody.innerHTML += `
            <tr>
              <td class="py-3">
                <span class="font-semibold text-[#1c1a17] block">${item.tenant_name}</span>
                <span class="text-[#1c1a17]/50 text-[10px] micro-label-muted">Unit ${item.unit_number} &bull; ${item.days_overdue} days overdue</span>
              </td>
              <td class="py-3 text-right font-serif font-semibold text-red-600 numeral-serif">
                KES ${item.balance.toLocaleString()}
              </td>
            </tr>
          `;
        });
      }
    }

    // Fetch YOY Chart Data
    const yoyRes = await window.apiRequest(`/reports/yoy-occupancy?building_id=${bldgId}`);
    renderYOYChart(yoyRes.labels, yoyRes.current_year, yoyRes.previous_year);

    // Fetch and show Pending Tenant Registrations
    loadPendingTenantList();

  } catch (err) {
    console.error(err);
  }
}

async function loadPendingTenantList() {
  const container = document.getElementById('pending-tenants-list');
  const badge = document.getElementById('pending-tenants-badge');
  if (!container) return;
  try {
    const res = await window.apiRequest('/auth/pending-tenants');
    const tenants = res.tenants || [];
    if (badge) badge.innerText = tenants.length;
    container.innerHTML = '';

    if (tenants.length === 0) {
      container.innerHTML = `<p class="text-xs text-[#1c1a17]/40 italic py-6 text-center">No pending registrations.</p>`;
      return;
    }

    tenants.forEach(t => {
      container.innerHTML += `
        <div class="flex items-center justify-between p-3 rounded-xl bg-[#ede9df]/30 border border-[#dfd9cd]/50">
          <div>
            <span class="font-semibold text-xs text-[#1c1a17] block">${t.full_name}</span>
            <span class="text-[10px] text-[#1c1a17]/50 block">${t.email}</span>
          </div>
          <a href="payments.html" class="px-2.5 py-1.5 rounded-full bg-[#c2593f]/10 text-[#c2593f] text-[10px] font-bold hover:bg-[#c2593f] hover:text-white transition">
            Review &rarr;
          </a>
        </div>
      `;
    });
  } catch (err) {
    container.innerHTML = `<p class="text-xs text-red-400 py-6 text-center">Could not load registrations.</p>`;
  }
}

function renderYOYChart(labels, currentYear, previousYear) {
  const canvas = document.getElementById('yoyChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (yoyChartInstance) yoyChartInstance.destroy();

  yoyChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: '2026 Occupancy Rate (%)',
          data: currentYear,
          borderColor: '#c2593f',
          backgroundColor: 'rgba(194, 89, 63, 0.08)',
          borderWidth: 3,
          fill: true,
          tension: 0.4
        },
        {
          label: '2025 Occupancy Rate (%)',
          data: previousYear,
          borderColor: '#dfd9cd',
          borderWidth: 2,
          borderDash: [5, 5],
          fill: false,
          tension: 0.4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 50, max: 100, grid: { color: 'rgba(223, 217, 205, 0.5)' } },
        x: { grid: { display: false } }
      }
    }
  });
}

/* ── Change Password Modal ── */
function openChangePwModal() {
  const form = document.getElementById('change-pw-form');
  if (form) form.reset();
  const errEl = document.getElementById('cp-error');
  if (errEl) errEl.classList.add('hidden');
  const modal = document.getElementById('modal-change-pw');
  if (modal) {
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }
}

function closeChangePwModal() {
  const modal = document.getElementById('modal-change-pw');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

async function submitChangePw(e) {
  e.preventDefault();
  const errEl = document.getElementById('cp-error');
  if (errEl) errEl.classList.add('hidden');
  const current  = document.getElementById('cp-current').value;
  const newPw    = document.getElementById('cp-new').value;
  const confirm  = document.getElementById('cp-confirm').value;

  if (newPw !== confirm) {
    if (errEl) {
      errEl.textContent = 'New passwords do not match.';
      errEl.classList.remove('hidden');
    }
    return;
  }
  const user = window.getCurrentUser && window.getCurrentUser();
  if (!user) {
    if (errEl) {
      errEl.textContent = 'Not logged in.';
      errEl.classList.remove('hidden');
    }
    return;
  }
  try {
    await window.apiRequest('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        email: user.email,
        current_password: current,
        new_password: newPw
      })
    });
    closeChangePwModal();
    window.showToast('Password changed! Please log in again with your new password.', 'success');
    setTimeout(() => {
      localStorage.removeItem('nrb_session');
      window.location.href = '/index.html';
    }, 2000);
  } catch (err) {
    if (errEl) {
      errEl.textContent = err.message || 'Failed to change password. Check your current password.';
      errEl.classList.remove('hidden');
    }
  }
}

/* ── Settings Modal Functions ── */
async function openSettingsModal() {
  try {
    const settings = await window.apiRequest('/settings');
    document.getElementById('set-copyright').value = settings.copyright_text || '© 2026 Nairobi Rentals . All rights reserved.';
    document.getElementById('set-phil-title').value = settings.philosophy_title || '';
    document.getElementById('set-phil-desc').value = settings.philosophy_description || '';
    document.getElementById('set-stat1-val').value = settings.stat1_value || '';
    document.getElementById('set-stat1-lbl').value = settings.stat1_label || '';
    document.getElementById('set-stat2-val').value = settings.stat2_value || '';
    document.getElementById('set-stat2-lbl').value = settings.stat2_label || '';
    document.getElementById('set-stat3-val').value = settings.stat3_value || '';
    document.getElementById('set-stat3-lbl').value = settings.stat3_label || '';
    
    document.getElementById('set-phil-quote').value = settings.phil_quote || '';
    document.getElementById('set-phil-quote-author').value = settings.phil_quote_author || '';
    document.getElementById('set-why-headline').value = settings.why_headline || '';
    document.getElementById('set-why-stat1-val').value = settings.why_stat1_val || '';
    document.getElementById('set-why-stat1-lbl').value = settings.why_stat1_lbl || '';
    document.getElementById('set-why-stat2-val').value = settings.why_stat2_val || '';
    document.getElementById('set-why-stat2-lbl').value = settings.why_stat2_lbl || '';

    // Pricing Tiers
    document.getElementById('set-price-std-title').value = settings.price_std_title || 'Standard Portfolio';
    document.getElementById('set-price-std-val').value = settings.price_std_val || 'KES 2,500';
    document.getElementById('set-price-std-sub').value = settings.price_std_sub || '/ month';
    document.getElementById('set-price-std-features').value = settings.price_std_features || 'Up to 30 units\nM-Pesa approval queue\nAutomatic email receipts\nCaretaker access';
    document.getElementById('set-price-ent-title').value = settings.price_ent_title || 'Multi-Building Estate';
    document.getElementById('set-price-ent-val').value = settings.price_ent_val || 'Custom Quote';
    document.getElementById('set-price-ent-features').value = settings.price_ent_features || 'Unlimited units & buildings\nCustom Paybill / Till integration\nDedicated onboarding support\nCustom report exports';

    try {
      const res = await window.apiRequest('/units');
      const units = res.units || [];
      if (units.length > 0) {
        const occupied = units.filter(u => u.status === 'occupied').length;
        const rate = ((occupied / units.length) * 100).toFixed(1);
        document.getElementById('set-stat2-val').value = `${rate}%`;
      } else {
        document.getElementById('set-stat2-val').value = '0%';
      }
    } catch (e) {
      document.getElementById('set-stat2-val').value = '0%';
    }

    const modal = document.getElementById('modal-settings');
    if (modal) {
      modal.classList.remove('hidden');
      modal.classList.add('flex');
    }
  } catch (err) {
    console.error(err);
  }
}

function closeSettingsModal() {
  const modal = document.getElementById('modal-settings');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

async function handleSaveSettings(e) {
  e.preventDefault();
  const payload = {
    copyright_text: document.getElementById('set-copyright').value,
    philosophy_title: document.getElementById('set-phil-title').value,
    philosophy_description: document.getElementById('set-phil-desc').value,
    stat1_value: document.getElementById('set-stat1-val').value,
    stat1_label: document.getElementById('set-stat1-lbl').value,
    stat2_label: document.getElementById('set-stat2-lbl').value,
    stat3_value: document.getElementById('set-stat3-val').value,
    stat3_label: document.getElementById('set-stat3-lbl').value,
    
    phil_quote: document.getElementById('set-phil-quote').value,
    phil_quote_author: document.getElementById('set-phil-quote-author').value,
    why_headline: document.getElementById('set-why-headline').value,
    why_stat1_val: document.getElementById('set-why-stat1-val').value,
    why_stat1_lbl: document.getElementById('set-why-stat1-lbl').value,
    why_stat2_val: document.getElementById('set-why-stat2-val').value,
    why_stat2_lbl: document.getElementById('set-why-stat2-lbl').value,

    price_std_title: document.getElementById('set-price-std-title').value,
    price_std_val: document.getElementById('set-price-std-val').value,
    price_std_sub: document.getElementById('set-price-std-sub').value,
    price_std_features: document.getElementById('set-price-std-features').value,
    price_ent_title: document.getElementById('set-price-ent-title').value,
    price_ent_val: document.getElementById('set-price-ent-val').value,
    price_ent_features: document.getElementById('set-price-ent-features').value
  };

  try {
    await window.apiRequest('/settings', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
    window.showToast('Platform settings saved successfully!', 'success');
    closeSettingsModal();
  } catch (err) {
    console.error(err);
  }
}

/* ── Edit Building Modal ── */
async function openEditBuildingModal() {
  const selectedBldgId = window.getBuildingFilter() || 'bldg-001';
  try {
    const res = await window.apiRequest('/buildings');
    const bldg = (res.buildings || []).find(b => b.id === selectedBldgId);
    if (bldg) {
      document.getElementById('edit-bldg-name').value = bldg.name;
      document.getElementById('edit-bldg-location').value = bldg.location;
      document.getElementById('modal-edit-building').classList.replace('hidden', 'flex');
    }
  } catch (err) {}
}

function closeEditBuildingModal() {
  document.getElementById('modal-edit-building').classList.replace('flex', 'hidden');
}

async function handleEditBuilding(e) {
  e.preventDefault();
  const selectedBldgId = window.getBuildingFilter() || 'bldg-001';
  const name = document.getElementById('edit-bldg-name').value.trim();
  const location = document.getElementById('edit-bldg-location').value.trim();
  try {
    await window.apiRequest(`/buildings/${selectedBldgId}`, {
      method: 'PUT',
      body: JSON.stringify({ name, location })
    });
    window.showToast('Building updated successfully!', 'success');
    closeEditBuildingModal();
    await loadDashboardData();
  } catch (err) {}
}

/* ── Add Property Modal Functions ── */
function openAddBuildingModal() {
  document.getElementById('add-bldg-name').value = '';
  document.getElementById('add-bldg-location').value = '';
  document.getElementById('add-bldg-floors').value = '4';
  document.getElementById('modal-add-building').classList.replace('hidden', 'flex');
}

function closeAddBuildingModal() {
  document.getElementById('modal-add-building').classList.replace('flex', 'hidden');
}

async function handleAddBuilding(e) {
  e.preventDefault();
  const name = document.getElementById('add-bldg-name').value.trim();
  const location = document.getElementById('add-bldg-location').value.trim();
  const total_floors = parseInt(document.getElementById('add-bldg-floors').value);
  try {
    await window.apiRequest('/buildings', {
      method: 'POST',
      body: JSON.stringify({ name, location, total_floors })
    });
    window.showToast('Property created successfully!', 'success');
    closeAddBuildingModal();
    await window.renderNavbar('dashboard');
    await loadDashboardData();
  } catch (err) {}
}

/* ── Add Unit Modal ── */
async function populateBuildingSelect(selectId) {
  const select = document.getElementById(selectId);
  if (!select) return;
  select.innerHTML = '<option value="">Loading properties...</option>';
  try {
    const res = await window.apiRequest('/buildings');
    const buildings = res.buildings || [];
    if (buildings.length === 0) {
      select.innerHTML = '<option value="">No properties created yet</option>';
      return;
    }
    select.innerHTML = buildings.map(b => `<option value="${b.id}">${b.name}</option>`).join('');
    const currentBldg = window.getBuildingFilter();
    if (currentBldg && buildings.some(b => b.id === currentBldg)) {
      select.value = currentBldg;
    }
  } catch (e) {
    select.innerHTML = '<option value="">Error loading properties</option>';
  }
}

async function openAddUnitModal() {
  await populateBuildingSelect('unit-building-select');
  document.getElementById('modal-add-unit').classList.replace('hidden', 'flex');
}

function closeAddUnitModal() {
  document.getElementById('modal-add-unit').classList.replace('flex', 'hidden');
}

async function handleAddUnit(e) {
  e.preventDefault();
  const building_id = document.getElementById('unit-building-select').value;
  if (!building_id) {
    window.showToast('Please select a property (building).', 'error');
    return;
  }
  const unit_number = document.getElementById('unit-number-input').value.trim();
  const floor = parseInt(document.getElementById('unit-floor-input').value);
  const rent_amount = parseFloat(document.getElementById('unit-rent-input').value);

  try {
    await window.apiRequest('/units', {
      method: 'POST',
      body: JSON.stringify({
        building_id,
        unit_number,
        floor,
        rent_amount,
        status: 'vacant',
        is_active: true
      })
    });
    window.showToast('Room unit added to active inventory!', 'success');
    closeAddUnitModal();
    await loadDashboardData();
  } catch (err) {}
}

/* ── Bulk Import Modal ── */
async function openBulkImportModal() {
  await populateBuildingSelect('bulk-building-select');
  document.getElementById('modal-bulk-import').classList.replace('hidden', 'flex');
}

function closeBulkImportModal() {
  document.getElementById('modal-bulk-import').classList.replace('flex', 'hidden');
}

async function handleBulkImport(e) {
  e.preventDefault();
  const building_id = document.getElementById('bulk-building-select').value;
  if (!building_id) {
    window.showToast('Please select a property (building).', 'error');
    return;
  }
  const text = document.getElementById('csv-content-input').value.trim();
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  const csv_data = [];
  for (const line of lines) {
    const parts = line.split(',').map(p => p.trim());
    if (parts.length >= 3) {
      csv_data.push({
        unit_number: parts[0],
        floor: parseInt(parts[1]),
        rent_amount: parseFloat(parts[2])
      });
    }
  }

  try {
    const res = await window.apiRequest('/units/bulk-import', {
      method: 'POST',
      body: JSON.stringify({ building_id, csv_data })
    });
    window.showToast(`Bulk imported ${res.imported_count} units!`, 'success');
    closeBulkImportModal();
    await loadDashboardData();
  } catch (err) {}
}

function togglePasswordVisibility(inputId, btnEl) {
  const input = document.getElementById(inputId);
  const icon = btnEl.querySelector('i');
  if (!input || !icon) return;
  if (input.type === 'password') {
    input.type = 'text';
    icon.setAttribute('data-lucide', 'eye-off');
  } else {
    input.type = 'password';
    icon.setAttribute('data-lucide', 'eye');
  }
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }
}
