/* Accessible show/hide controls for every password input on public pages. */
(function () {
  function addPasswordToggles() {
    document.querySelectorAll('input[type="password"]:not([data-password-toggle-ready])').forEach((input) => {
      if (input.parentElement?.querySelector('button[id^="btn-toggle-"]')) return;
      input.dataset.passwordToggleReady = 'true';
      input.style.paddingRight = '3.25rem';

      const container = document.createElement('div');
      container.style.cssText = 'position:relative;width:100%;';
      input.parentNode.insertBefore(container, input);
      container.appendChild(input);

      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = 'Show';
      button.title = 'Show password';
      button.setAttribute('aria-label', 'Show password');
      button.style.cssText = 'position:absolute;right:.7rem;top:50%;transform:translateY(-50%);border:0;background:transparent;color:var(--fg-ink);font-size:.72rem;font-weight:700;cursor:pointer;line-height:1;padding:.2rem;';
      button.addEventListener('click', () => {
        const visible = input.type === 'text';
        input.type = visible ? 'password' : 'text';
        button.textContent = visible ? 'Show' : 'Hide';
        button.title = visible ? 'Show password' : 'Hide password';
        button.setAttribute('aria-label', button.title);
      });
      container.appendChild(button);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addPasswordToggles);
  else addPasswordToggles();
}());
