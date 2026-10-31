
  (function(){
    var activeEmail = (localStorage.getItem('travelverse_current_user_email') || '').trim().toLowerCase();
    var isAuth = localStorage.getItem('travelverse_session_active') === 'true';
    if (!isAuth || !activeEmail || activeEmail === 'null' || activeEmail === 'undefined') {
      localStorage.clear();
      window.location.href = 'login.html';
    }
  })();
