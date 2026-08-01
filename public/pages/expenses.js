let expensesList = [];

const CATEGORY_ICONS = {
  security: '🛡', water: '💧', electricity: '⚡',
  garbage: '🗑', repairs: '🔧', salaries: '👤', other: '📄'
};

document.addEventListener('DOMContentLoaded', async () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Setup submit listener for expense form
  const form = document.getElementById('log-expense-form');
  if (form) {
    form.addEventListener('submit', handleLogExpense);
  }

  window.ThemeManager && window.ThemeManager.init();
  window.PWAManager && window.PWAManager.init();
  if (!window.requireRole(['landlord'])) return;
  await window.renderNavbar('expenses');
  await populateBuildingDropdown();
  await loadExpenses();
  window.addEventListener('buildingChanged', loadExpenses);
});

async function populateBuildingDropdown() {
  const select = document.getElementById('exp-bldg');
  if (!select) return;
  try {
    const res = await window.apiRequest('/buildings');
    const buildings = res.buildings || [];
    if (buildings.length > 0) {
      select.innerHTML = buildings.map(b => `<option value="${b.id}">${b.name}</option>`).join('');
    } else {
      select.innerHTML = `<option value="">No properties found</option>`;
    }
  } catch (err) {
    console.error('Failed to load buildings for expenses form:', err);
  }
}

async function loadExpenses() {
  const bldgId = window.getBuildingFilter();
  try {
    const res = await window.apiRequest(`/expenses?building_id=${bldgId}`);
    expensesList = res.expenses || [];
    renderExpensesTable();
  } catch (err) { console.error(err); }
}

function renderExpensesTable() {
  const tbody = document.getElementById('expenses-table-body');
  const summaryEl = document.getElementById('category-summary');
  if (!tbody || !summaryEl) return;
  tbody.innerHTML = '';
  summaryEl.innerHTML = '';

  if (!expensesList.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="py-10 text-center text-[#1c1a17]/40 font-serif text-lg">No expenses logged yet.</td></tr>`;
    const sumEl = document.getElementById('total-expenses-sum');
    if (sumEl) sumEl.innerText = 'KES 0';
    return;
  }

  let sum = 0;
  const byCategory = {};

  expensesList.forEach(e => {
    sum += e.amount;
    byCategory[e.category] = (byCategory[e.category] || 0) + e.amount;

    tbody.innerHTML += `
      <tr class="hover:bg-[#ede9df]/30 transition">
        <td class="py-3.5 text-[#1c1a17]/60 tabular-nums">${e.date}</td>
        <td class="py-3.5 font-medium text-[#1c1a17]">${e.building_name || 'N/A'}</td>
        <td class="py-3.5">
          <span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-[#ede9df] text-[#1c1a17]/80 capitalize">
            ${CATEGORY_ICONS[e.category] || '📄'} ${e.category}
          </span>
        </td>
        <td class="py-3.5 text-[#1c1a17]/60 max-w-xs truncate">${e.description || '—'}</td>
        <td class="py-3.5 text-right font-serif font-semibold text-[#1c1a17] numeral-serif">
          KES ${e.amount.toLocaleString()}
        </td>
        <td class="py-3.5 text-right"><button class="delete-expense text-xs text-red-600 hover:underline" data-expense-id="${e.id}">Delete</button></td>
      </tr>`;
  });
  tbody.querySelectorAll('.delete-expense').forEach(btn => btn.addEventListener('click', () => deleteExpense(btn.dataset.expenseId)));

  const sumEl = document.getElementById('total-expenses-sum');
  if (sumEl) sumEl.innerText = `KES ${sum.toLocaleString()}`;

  // Category summary pills
  Object.entries(byCategory).sort((a,b) => b[1]-a[1]).forEach(([cat, total]) => {
    summaryEl.innerHTML += `
      <div class="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-[#dfd9cd] bg-[#ede9df]/60 text-[10px]">
        <span>${CATEGORY_ICONS[cat] || '📄'}</span>
        <span class="font-semibold uppercase tracking-wider text-[#1c1a17]/70">${cat}</span>
        <span class="font-serif numeral-serif font-medium text-[#c2593f]">KES ${total.toLocaleString()}</span>
      </div>`;
  });
}

async function deleteExpense(expenseId) {
  if (!confirm('Delete this expense record?')) return;
  try { await window.apiRequest(`/expenses/${expenseId}`, { method: 'DELETE' }); await loadExpenses(); window.showToast('Expense deleted.', 'success'); }
  catch (err) { window.showToast(err.message || 'Could not delete expense.', 'error'); }
}

async function handleLogExpense(e) {
  e.preventDefault();
  const payload = {
    building_id: document.getElementById('exp-bldg').value,
    category: document.getElementById('exp-cat').value,
    amount: parseFloat(document.getElementById('exp-amount').value),
    date: document.getElementById('exp-date').value,
    description: document.getElementById('exp-desc').value,
    receipt_url: ''
  };
  try {
    await window.apiRequest('/expenses', { method: 'POST', body: JSON.stringify(payload) });
    window.showToast('Expense saved to ledger.', 'success');
    e.target.reset();
    document.getElementById('exp-date').value = new Date().toISOString().slice(0, 10);
    await loadExpenses();
  } catch (err) {}
}
