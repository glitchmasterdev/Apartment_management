(function(){
  const s = localStorage.getItem('nrb_session');
  if (!s) {
    window.location.href = 'index.html?error=login_required';
  }
})();
