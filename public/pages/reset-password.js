document.addEventListener('DOMContentLoaded', () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }

  // Parse query token
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token');

  const form = document.getElementById('reset-pw-form');
  const msgEl = document.getElementById('rp-message');

  function showMessage(text, isError = false) {
    if (!msgEl) return;
    msgEl.textContent = text;
    msgEl.className = `text-sm p-3.5 rounded-xl ${isError ? 'bg-red-50 text-red-700 dark:bg-red-950/20 dark:text-red-400' : 'bg-green-50 text-green-700 dark:bg-green-950/20 dark:text-green-400'}`;
    msgEl.classList.remove('hidden');
  }

  if (!token) {
    showMessage('Invalid or missing security token. Please request a new password reset link.', true);
    if (form) {
      const btn = form.querySelector('button[type="submit"]');
      if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
      }
    }
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (msgEl) msgEl.classList.add('hidden');

      const password = document.getElementById('rp-password').value;
      const confirm = document.getElementById('rp-confirm').value;

      if (password !== confirm) {
        showMessage('Passwords do not match.', true);
        return;
      }

      if (password.length < 8) {
        showMessage('Password must be at least 8 characters long.', true);
        return;
      }
      if (!/[a-zA-Z]/.test(password) || !/[0-9]/.test(password)) {
        showMessage('Password must contain both letters and numbers.', true);
        return;
      }

      try {
        const response = await fetch('/api/landlord/reset-password', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ token, new_password: password })
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || 'Failed to reset password.');
        }

        showMessage('Password reset successfully! Redirecting you to login...');
        setTimeout(() => {
          window.location.href = '/index.html?login=true';
        }, 2000);
      } catch (err) {
        showMessage(err.message, true);
      }
    });
  }

  // Toggle buttons
  const btnTogglePassword = document.getElementById('btn-toggle-rp-password');
  if (btnTogglePassword) {
    btnTogglePassword.addEventListener('click', function() {
      togglePasswordVisibility('rp-password', btnTogglePassword);
    });
  }

  const btnToggleConfirm = document.getElementById('btn-toggle-rp-confirm');
  if (btnToggleConfirm) {
    btnToggleConfirm.addEventListener('click', function() {
      togglePasswordVisibility('rp-confirm', btnToggleConfirm);
    });
  }
});

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
