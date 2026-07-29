document.addEventListener('DOMContentLoaded', () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  const btnReset = document.getElementById('btn-reset-demo');
  if (btnReset) {
    btnReset.addEventListener('click', resetDemoData);
  }

  const btnDashboard = document.getElementById('btn-enter-dashboard');
  if (btnDashboard) {
    btnDashboard.addEventListener('click', () => enterDemo('/dashboard.html'));
  }

  const btnPayments = document.getElementById('btn-enter-payments');
  if (btnPayments) {
    btnPayments.addEventListener('click', () => enterDemo('/payments.html'));
  }

  const btnReports = document.getElementById('btn-enter-reports');
  if (btnReports) {
    btnReports.addEventListener('click', () => enterDemo('/reports.html'));
  }
});

async function enterDemo(targetUrl) {
  try {
    const res = await window.apiRequest('/demo/login');
    if (res.user) {
      window.setCurrentUser(res.user);
      window.location.href = targetUrl;
    }
  } catch (err) {
    window.showToast('Could not initialize demo session: ' + err.message, 'error');
  }
}

async function resetDemoData() {
  try {
    const res = await window.apiRequest('/demo/reset', { method: 'POST' });
    window.showToast(res.message || 'Demo data reset successfully!', 'success');
  } catch (err) {
    window.showToast('Reset failed: ' + err.message, 'error');
  }
}
