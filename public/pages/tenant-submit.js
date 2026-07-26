document.addEventListener('DOMContentLoaded', () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  const form = document.getElementById('public-submit-form');
  if (form) {
    form.addEventListener('submit', handlePublicSubmit);
  }
});

async function handlePublicSubmit(e) {
  e.preventDefault();
  const payload = {
    unit_number: document.getElementById('public-unit').value,
    phone_number: document.getElementById('public-phone').value,
    amount_paid: parseFloat(document.getElementById('public-amount').value),
    mpesa_code: document.getElementById('public-mpesa').value,
    tenant_message: document.getElementById('public-message').value,
    receipt_photo: 'mock-uploaded-receipt'
  };

  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-circle" class="w-4 h-4 animate-spin"></i> Submitting…`;
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  try {
    const res = await window.apiRequest('/payments/public-submit', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    window.showToast(res.message, 'success');
    e.target.reset();
  } catch (err) {
    window.showToast('Submission failed. Please check your unit number and try again.', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="send" class="w-4 h-4"></i> Submit Payment Proof`;
    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }
}
