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
  const buildingQuery = bldgId ? `?building_id=${encodeURIComponent(bldgId)}` : '';

  try {
    // Dashboard KPIs
    const kpiRes = await window.apiRequest(`/reports/dashboard${buildingQuery}`, { cache: 'no-store' });
    const k = kpiRes.kpis || {};
    document.getElementById('rep-total-units').innerText = k.total_units ?? 0;
    document.getElementById('rep-occupancy').innerText = `${k.occupancy_rate ?? 0}%`;
    document.getElementById('rep-revenue').innerText = `KES ${(k.monthly_revenue ?? 0).toLocaleString()}`;
    document.getElementById('rep-rent-received').innerText = `KES ${(k.rent_received ?? 0).toLocaleString()}`;

    // Arrears are the outstanding amount for the active payment cycle.
    const arr = kpiRes.top_arrears || [];
    document.getElementById('rep-arrears').innerText = `KES ${(k.total_arrears ?? 0).toLocaleString()}`;

    // Arrears detail table
    const tbody = document.getElementById('arrears-detail-body');
    if (tbody) {
      tbody.innerHTML = '';
      if (!arr.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="py-8 text-center text-[#1c1a17]/40 font-serif text-lg">No overdue balances — all tenants current. </td></tr>`;
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

  } catch (err) { console.error(err); }
}

function downloadCSVReport() {
  const buildingFilter = document.getElementById('nav-building-filter');
  const buildingName = buildingFilter?.selectedOptions?.[0]?.textContent?.trim() || 'All Buildings';
  const getMetric = (id) => document.getElementById(id)?.textContent?.trim() || '0';
  const csvContent = [
    'Report Date,Building,Metric,Value',
    `${new Date().toISOString().slice(0,10)},"${buildingName.replace(/"/g, '""')}",Total Units,"${getMetric('rep-total-units')}"`,
    `${new Date().toISOString().slice(0,10)},"${buildingName.replace(/"/g, '""')}",Occupancy Rate,"${getMetric('rep-occupancy')}"`,
    `${new Date().toISOString().slice(0,10)},"${buildingName.replace(/"/g, '""')}",Expected Monthly Revenue,"${getMetric('rep-revenue')}"`,
    `${new Date().toISOString().slice(0,10)},"${buildingName.replace(/"/g, '""')}",Rent Received This Cycle,"${getMetric('rep-rent-received')}"`,
    `${new Date().toISOString().slice(0,10)},"${buildingName.replace(/"/g, '""')}",Total Arrears,"${getMetric('rep-arrears')}"`,
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
