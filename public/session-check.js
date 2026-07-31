// The tenant portal owns its unauthenticated sign-in/sign-up experience.
// Do not redirect new tenants away before they can create an account.
(function(){
  const page = window.location.pathname.split('/').pop() || '';
  if (page === 'tenant-portal.html' || page === 'reset-password.html' || page === 'verify-email.html') return;
  const s = localStorage.getItem('nrb_session');
  if (!s) window.location.href = 'index.html?error=login_required';
})();
