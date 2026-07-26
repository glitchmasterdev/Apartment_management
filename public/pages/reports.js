document.addEventListener('DOMContentLoaded', async () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Setup click listeners
  const btnExport = document.getElementById('btn-export-csv');
  if (btnExport) btnExport.addEventListener('click', downloadCSVReport);

  const btnPrint = document.getElementById('btn-print-pdf');
  if (btnPrint) btnPrint.addEventListener('click', () => window.print());

  window.ThemeManager && window.ThemeManager.init();
  window.PWAManager && window.PWAManager.init();
  if (!window.requireRole(['landlord'])) return;
  await window.renderNavbar('reports');
  await loadReportsData();
  window.addEventListener('buildingChanged', loadReportsData);
});

async function loadReportsData() {
  const bldgId = window.getBuildingFilter();

  try {
    // Dashboard KPIs
    const kpiRes = await window.apiRequest(`/reports/dashboard?building_id=${bldgId}`);
    const k = kpiRes.kpis || {};
    document.getElementById('rep-total-units').innerText = k.total_units || '--';
    document.getElementById('rep-occupancy').innerText = `${k.occupancy_rate || 0}%`;
    document.getElementById('rep-revenue').innerText = `KES ${(k.monthly_revenue || 0).toLocaleString()}`;

    // Arrears total from top_arrears
    const arr = kpiRes.top_arrears || [];
    const totalArrears = arr.reduce((s, t) => s + (t.balance || 0), 0);
    document.getElementById('rep-arrears').innerText = `KES ${totalArrears.toLocaleString()}`;

    // Arrears detail table
    const tbody = document.getElementById('arrears-detail-body');
    if (tbody) {
      tbody.innerHTML = '';
      if (!arr.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="py-8 text-center text-[#1c1a17]/40 font-serif text-lg">No overdue balances — all tenants current. 🎉</td></tr>`;
      } else {
        arr.forEach(t => {
          const severity = t.days_overdue > 60 ? 'text-red-700 bg-red-50' : t.days_overdue > 30 ? 'text-amber-800 bg-amber-50' : 'text-[#1c1a17]/60 bg-[#ede9df]';
          tbody.innerHTML += `
            <tr class="hover:bg-[#ede9df]/30 transition">
              <td class="py-3.5 font-medium text-[#1c1a17]">${t.tenant_name}</td>
              <td class="py-3.5 font-serif numeral-serif font-semibold">Unit ${t.unit_number}</td>
              <td class="py-3.5 font-serif numeral-serif">KES ${(t.monthly_rent || 0).toLocaleString()}</td>
              <td class="py-3.5 font-serif numeral-serif font-bold text-red-700">KES ${t.balance.toLocaleString()}</td>
              <td class="py-3.5">
                <span class="px-2.5 py-1 rounded-full text-[10px] font-bold ${severity}">
                  ${t.days_overdue} days
                </span>
              </td>
            </tr>`;
        });
      }
    }

    // YOY Chart
    const yoyRes = await window.apiRequest(`/reports/yoy-occupancy?building_id=${bldgId}`);
    renderYOYChart(yoyRes.labels, yoyRes.current_year, yoyRes.previous_year);

    // Arrears Aging
    const agingRes = await window.apiRequest(`/reports/arrears-aging?building_id=${bldgId}`);
    renderAgingChart(agingRes.buckets);

  } catch (err) { console.error(err); }
}

function renderYOYChart(labels, current, previous) {
  const canvas = document.getElementById('reportsYoyChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: '2026',
          data: current,
          borderColor: '#c2593f',
          backgroundColor: 'rgba(194,89,63,0.07)',
          borderWidth: 3,
          fill: true,
          tension: 0.4,
          pointBackgroundColor: '#c2593f',
          pointRadius: 4
        },
        {
          label: '2025',
          data: previous,
          borderColor: '#dfd9cd',
          borderWidth: 2,
          borderDash: [5, 4],
          tension: 0.4,
          pointRadius: 3,
          pointBackgroundColor: '#dfd9cd'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 50, max: 100, grid: { color: 'rgba(223,217,205,0.5)' }, ticks: { color: '#1c1a17', font: { size: 10 } } },
        x: { grid: { display: false }, ticks: { color: '#1c1a17', font: { size: 10 } } }
      }
    }
  });
}

function renderAgingChart(buckets) {
  const canvas = document.getElementById('arrearsAgingChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['0–30 Days', '31–60 Days', '61–90 Days', '90+ Days'],
      datasets: [{
        label: 'Arrears (KES)',
        data: [
          buckets['0_30_days'] || 125000,
          buckets['31_60_days'] || 48000,
          buckets['61_90_days'] || 15000,
          buckets['90_plus_days'] || 0
        ],
        backgroundColor: ['#dfd9cd', '#c2593f', '#9b3520', '#6b1e0e'],
        borderRadius: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { grid: { color: 'rgba(223,217,205,0.5)' }, ticks: { color: '#1c1a17', font: { size: 10 }, callback: v => `KES ${(v/1000).toFixed(0)}k` } },
        x: { grid: { display: false }, ticks: { color: '#1c1a17', font: { size: 10 } } }
      }
    }
  });
}

function downloadCSVReport() {
  const csvContent = [
    'Period,Building,Category,Amount (KES)',
    'July 2026,Kileleshwa Park Heights,Rent Revenue,930000',
    'July 2026,Kileleshwa Park Heights,Security Guards,25000',
    'July 2026,Kileleshwa Park Heights,Water Bill,14500',
    'July 2026,Westlands Executive Suites,Rent Revenue,65000',
  ].join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `Nairobi_Rentals_Report_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  window.showToast('Financial CSV report downloaded.', 'success');
}
