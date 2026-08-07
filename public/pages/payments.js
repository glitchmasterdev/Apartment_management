let pendingPayments = [];
let pendingTenants = [];
let rawUnitsData = [];

document.addEventListener('DOMContentLoaded', async () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Setup click listeners for switcher tabs
  const tabBtnPmts = document.getElementById('tab-btn-payments');
  if (tabBtnPmts) tabBtnPmts.addEventListener('click', () => switchTab('payments'));

  const tabBtnTenants = document.getElementById('tab-btn-tenants');
  if (tabBtnTenants) tabBtnTenants.addEventListener('click', () => switchTab('tenants'));

  // Header actions
  const btnBulkApprove = document.getElementById('btn-bulk-approve');
  if (btnBulkApprove) btnBulkApprove.addEventListener('click', handleBulkApprove);

  const btnStartPaymentCycle = document.getElementById('btn-start-payment-cycle');
  if (btnStartPaymentCycle) btnStartPaymentCycle.addEventListener('click', startNewPaymentCycle);

  const btnOpenReject = document.getElementById('btn-open-reject-modal');
  if (btnOpenReject) btnOpenReject.addEventListener('click', openRejectModal);

  // Table refresh buttons
  const btnRefreshPmts = document.getElementById('btn-refresh-payments');
  if (btnRefreshPmts) btnRefreshPmts.addEventListener('click', loadPendingPayments);

  const btnRefreshTenants = document.getElementById('btn-refresh-tenants');
  if (btnRefreshTenants) btnRefreshTenants.addEventListener('click', loadPendingTenants);

  // Checkbox select all
  const chkSelectAll = document.getElementById('select-all-payments');
  if (chkSelectAll) chkSelectAll.addEventListener('change', (e) => toggleSelectAll(e.target));

  // Reject payment modal handlers
  const formRejectPayment = document.getElementById('reject-payment-form');
  if (formRejectPayment) formRejectPayment.addEventListener('submit', handleBulkRejectSubmit);

  const btnCancelReject = document.getElementById('btn-cancel-reject-modal');
  if (btnCancelReject) btnCancelReject.addEventListener('click', closeRejectModal);

  // Approve tenant modal handlers
  const formApproveTenant = document.getElementById('approve-tenant-form');
  if (formApproveTenant) formApproveTenant.addEventListener('submit', handleApproveTenantSubmit);

  const btnCloseApprModal = document.getElementById('btn-close-approve-tenant');
  if (btnCloseApprModal) btnCloseApprModal.addEventListener('click', closeApproveTenantModal);

  const btnCancelApprModal = document.getElementById('btn-cancel-approve-tenant');
  if (btnCancelApprModal) btnCancelApprModal.addEventListener('click', closeApproveTenantModal);

  const btnRejectTenant = document.getElementById('btn-reject-tenant');
  if (btnRejectTenant) btnRejectTenant.addEventListener('click', handleRejectTenant);

  // Select onchange listeners
  const selectBuilding = document.getElementById('appr-building-select');
  if (selectBuilding) {
    selectBuilding.addEventListener('change', (e) => loadVacantUnits(e.target.value));
  }

  const selectUnit = document.getElementById('appr-unit-select');
  if (selectUnit) {
    selectUnit.addEventListener('change', (e) => updateRentField(e.target));
  }

  // Event delegation on tables
  const tbodyPmts = document.getElementById('payments-table-body');
  if (tbodyPmts) {
    tbodyPmts.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action="approve"]');
      if (btn) approveSingle(btn.dataset.paymentId);
    });
  }

  const tbodyTenants = document.getElementById('tenants-table-body');
  if (tbodyTenants) {
    tbodyTenants.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action="review"]');
      if (btn) {
        openApproveTenantModal(btn.dataset.tenantId, btn.dataset.tenantName);
      }
    });
  }

  window.ThemeManager && window.ThemeManager.init();
  window.PWAManager && window.PWAManager.init();
  if (!window.requireRole(['landlord', 'caretaker'])) return;
  await window.renderNavbar('payments');
  await loadPendingPayments();
  window.addEventListener('buildingChanged', loadPendingPayments);
});

// Switch between Payments and Tenants tabs
function switchTab(tab) {
  const pPanel = document.getElementById('tab-panel-payments');
  const tPanel = document.getElementById('tab-panel-tenants');
  const pBtn = document.getElementById('tab-btn-payments');
  const tBtn = document.getElementById('tab-btn-tenants');
  const actions = document.getElementById('payment-header-actions');

  if (tab === 'payments') {
    if (pPanel) pPanel.classList.remove('hidden');
    if (tPanel) tPanel.classList.add('hidden');
    if (actions) actions.classList.remove('hidden');
    if (pBtn) pBtn.className = "py-3 text-sm font-bold uppercase tracking-wider border-b-2 border-[#c2593f] text-[#c2593f] transition";
    if (tBtn) tBtn.className = "py-3 text-sm font-bold uppercase tracking-wider border-b-2 border-transparent text-[#1c1a17]/50 hover:text-[#1c1a17] transition";
  } else {
    if (pPanel) pPanel.classList.add('hidden');
    if (tPanel) tPanel.classList.remove('hidden');
    if (actions) actions.classList.add('hidden');
    if (tBtn) tBtn.className = "py-3 text-sm font-bold uppercase tracking-wider border-b-2 border-[#c2593f] text-[#c2593f] transition";
    if (pBtn) pBtn.className = "py-3 text-sm font-bold uppercase tracking-wider border-b-2 border-transparent text-[#1c1a17]/50 hover:text-[#1c1a17] transition";
    loadPendingTenants();
  }
}

/* ─── PAYMENT APPROVAL QUEUE ─── */
async function loadPendingPayments() {
  const bldgId = window.getBuildingFilter();
  try {
    const res = await window.apiRequest(`/payments/pending?building_id=${bldgId}`);
    pendingPayments = res.pending_payments || [];
    const badge = document.getElementById('pmt-count-badge');
    if (badge) badge.innerText = pendingPayments.length;
    renderPaymentsTable();
  } catch (err) {
    console.error(err);
  }
}

function renderPaymentsTable() {
  const tbody = document.getElementById('payments-table-body');
  if (!tbody) return;
  const pill = document.getElementById('pending-count-pill');
  if (pill) pill.innerText = `${pendingPayments.length} Pending`;
  tbody.innerHTML = '';

  if (pendingPayments.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="py-16 text-center">
          <i data-lucide="check-circle-2" class="w-10 h-10 text-emerald-500 mx-auto mb-3"></i>
          <p class="font-serif text-xl text-[#1c1a17]/50">Queue is clear. All payments verified.</p>
        </td>
      </tr>`;
    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
    return;
  }

  pendingPayments.forEach(p => {
    const time = new Date(p.payment_date).toLocaleString('en-KE', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
    tbody.innerHTML += `
      <tr class="hover:bg-[#ede9df]/30 transition">
        <td class="py-4">
          <input type="checkbox" value="${p.id}" class="payment-checkbox rounded border-[#dfd9cd] text-[#c2593f] focus:ring-[#c2593f]" />
        </td>
        <td class="py-4 font-serif font-semibold text-sm text-[#1c1a17] numeral-serif">Unit ${p.unit_number}</td>
        <td class="py-4 font-medium text-[#1c1a17]">${p.tenant_name}
          <span class="text-[10px] text-[#1c1a17]/40 block">${p.phone_number}</span>
        </td>
        <td class="py-4">
          <span class="font-mono font-bold px-2.5 py-1 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs">${p.mpesa_code}</span>
        </td>
        <td class="py-4 font-serif font-semibold text-sm text-[#1c1a17] numeral-serif">KES ${p.amount_paid.toLocaleString()}</td>
        <td class="py-4 text-[#1c1a17]/50 text-[11px]">${time}</td>
        <td class="py-4 text-[#1c1a17]/50 italic max-w-[140px] truncate">${p.tenant_message || '—'}</td>
        <td class="py-4 text-right">
          <button data-action="approve" data-payment-id="${p.id}"
            class="px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-900 font-bold text-[11px] hover:bg-emerald-600 hover:text-white transition">
            Approve
          </button>
        </td>
      </tr>`;
  });
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }
}

function toggleSelectAll(master) {
  document.querySelectorAll('.payment-checkbox').forEach(cb => cb.checked = master.checked);
}

function getSelectedIds() {
  const ids = [];
  document.querySelectorAll('.payment-checkbox:checked').forEach(cb => ids.push(cb.value));
  return ids;
}

async function startNewPaymentCycle() {
  if (!confirm('Start a new payment cycle? Approved payment history will be retained, while Rent Received starts again at KES 0.')) return;
  const button = document.getElementById('btn-start-payment-cycle');
  try {
    if (button) button.disabled = true;
    const result = await window.apiRequest('/reports/monthly-cycle/close', { method: 'POST' });
    window.showToast(result.message || 'New payment cycle started.', 'success');
  } catch (err) {
    window.showToast(err.message || 'Could not start a new payment cycle.', 'error');
  } finally {
    if (button) button.disabled = false;
  }
}

async function approveSingle(id) {
  try {
    await window.apiRequest('/payments/approve', {
      method: 'POST',
      body: JSON.stringify({ payment_ids: [id] })
    });
    window.showToast('Payment approved & receipt emailed!', 'success');
    await loadPendingPayments();
  } catch (err) {}
}

async function handleBulkApprove() {
  const ids = getSelectedIds();
  if (!ids.length) return window.showToast('Select at least one payment to approve.', 'error');
  try {
    const res = await window.apiRequest('/payments/approve', {
      method: 'POST', body: JSON.stringify({ payment_ids: ids })
    });
    window.showToast(`Approved ${res.approved_count} payments — receipts sent.`, 'success');
    await loadPendingPayments();
  } catch (err) {}
}

function openRejectModal() {
  if (!getSelectedIds().length) return window.showToast('Select at least one payment to reject.', 'error');
  const modal = document.getElementById('modal-reject');
  if (modal) modal.classList.replace('hidden', 'flex');
}

function closeRejectModal() {
  const modal = document.getElementById('modal-reject');
  if (modal) modal.classList.replace('flex', 'hidden');
}

async function handleBulkRejectSubmit(e) {
  e.preventDefault();
  const ids = getSelectedIds();
  const reason = document.getElementById('reject-reason-input').value;
  try {
    const res = await window.apiRequest('/payments/reject', {
      method: 'POST', body: JSON.stringify({ payment_ids: ids, reason })
    });
    window.showToast(`Rejected ${res.rejected_count} payments — reason emailed.`, 'success');
    closeRejectModal();
    await loadPendingPayments();
  } catch (err) {}
}

/* ─── TENANT VERIFICATION QUEUE ─── */
async function loadPendingTenants() {
  try {
    const res = await window.apiRequest('/auth/pending-tenants');
    pendingTenants = res.tenants || [];
    const badge = document.getElementById('tenant-count-badge');
    if (badge) badge.innerText = pendingTenants.length;
    renderTenantsTable();
  } catch (err) {
    console.error(err);
  }
}

function renderTenantsTable() {
  const tbody = document.getElementById('tenants-table-body');
  if (!tbody) return;
  const pill = document.getElementById('pending-tenants-pill');
  if (pill) pill.innerText = `${pendingTenants.length} Pending`;
  tbody.innerHTML = '';

  if (pendingTenants.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="py-16 text-center">
          <i data-lucide="users" class="w-10 h-10 text-[#c2593f] mx-auto mb-3"></i>
          <p class="font-serif text-xl text-[#1c1a17]/50">No pending tenant verifications.</p>
        </td>
      </tr>`;
    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
    return;
  }

  pendingTenants.forEach(t => {
    tbody.innerHTML += `
      <tr class="hover:bg-[#ede9df]/30 transition">
        <td class="py-4 font-semibold text-[#1c1a17]">${t.full_name}</td>
        <td class="py-4 text-[#1c1a17]/70">${t.email}</td>
        <td class="py-4 text-[#1c1a17]/70">${t.phone_number || '—'}</td>
        <td class="py-4 text-[#1c1a17]/50">Tenant Self Registered</td>
        <td class="py-4 text-right">
          <button data-action="review" data-tenant-id="${t.id}" data-tenant-name="${t.full_name.replace(/'/g, "&apos;")}"
            class="px-3 py-1.5 rounded-full bg-emerald-100 text-emerald-900 font-bold text-[11px] hover:bg-emerald-600 hover:text-white transition">
            Approve & Assign
          </button>
        </td>
      </tr>`;
  });
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }
}

async function openApproveTenantModal(id, name) {
  const modal = document.getElementById('modal-approve-tenant');
  const tenantIdInput = document.getElementById('appr-tenant-id');
  const tenantNameInput = document.getElementById('appr-tenant-name');
  const leaseStartInput = document.getElementById('appr-lease-start');

  if (tenantIdInput) tenantIdInput.value = id;
  if (tenantNameInput) tenantNameInput.value = name;
  if (leaseStartInput) leaseStartInput.value = new Date().toISOString().split('T')[0];

  // Populate buildings dropdown
  try {
    const res = await window.apiRequest('/buildings');
    const select = document.getElementById('appr-building-select');
    if (select) {
      select.innerHTML = '<option value="">Choose Building...</option>';
      (res.buildings || []).forEach(b => {
        select.innerHTML += `<option value="${b.id}">${b.name}</option>`;
      });
    }
  } catch (err) {}

  // Pre-load raw units list
  try {
    const res = await window.apiRequest('/units');
    rawUnitsData = res.units || [];
  } catch (err) {}

  if (modal) modal.classList.replace('hidden', 'flex');
}

function closeApproveTenantModal() {
  const modal = document.getElementById('modal-approve-tenant');
  if (modal) modal.classList.replace('flex', 'hidden');
}

function loadVacantUnits(buildingId) {
  const select = document.getElementById('appr-unit-select');
  if (!select) return;
  select.innerHTML = '<option value="">Choose Unit...</option>';
  if (!buildingId) return;

  const vacant = rawUnitsData.filter(u => u.building_id === buildingId && u.status === 'vacant');
  vacant.forEach(u => {
    select.innerHTML += `<option value="${u.id}" data-rent="${u.rent_amount}">Unit ${u.unit_number} (KES ${u.rent_amount.toLocaleString()})</option>`;
  });
}

function updateRentField(select) {
  const option = select.options[select.selectedIndex];
  const rentInput = document.getElementById('appr-rent');
  if (option && option.dataset.rent && rentInput) {
    rentInput.value = option.dataset.rent;
  }
}

async function handleApproveTenantSubmit(e) {
  e.preventDefault();
  const tenantId = document.getElementById('appr-tenant-id').value;
  const unitId = document.getElementById('appr-unit-select').value;
  const monthly_rent = parseFloat(document.getElementById('appr-rent').value);
  const lease_start_date = document.getElementById('appr-lease-start').value;

  try {
    await window.apiRequest(`/auth/approve-tenant/${tenantId}`, {
      method: 'POST',
      body: JSON.stringify({ unit_id: unitId, monthly_rent, lease_start_date })
    });
    window.showToast('Tenant account approved and welcome email dispatched!', 'success');
    closeApproveTenantModal();
    await loadPendingTenants();
    await loadPendingPayments();
  } catch (err) {}
}

async function handleRejectTenant() {
  const tenantId = document.getElementById('appr-tenant-id').value;
  const name = document.getElementById('appr-tenant-name').value;
  if (!confirm(`Are you sure you want to reject and delete the registration for ${name}?`)) return;

  try {
    await window.apiRequest(`/auth/reject-tenant/${tenantId}`, { method: 'POST' });
    window.showToast('Tenant registration rejected and removed.', 'info');
    closeApproveTenantModal();
    await loadPendingTenants();
  } catch (err) {}
}
