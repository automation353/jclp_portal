/* Shared shell behaviour: sidebar, toasts, Refresh All status. */
(function () {
  // ---- sidebar: collapse (desktop) / slide-in (mobile)
  const body = document.body;
  const toggle = document.getElementById('nav-toggle');
  if (toggle) toggle.addEventListener('click', () => {
    body.classList.toggle('nav-mini');
    try { localStorage.setItem('nongrn-nav', body.classList.contains('nav-mini') ? 'mini' : 'full'); } catch (e) {}
  });
  const open = document.getElementById('nav-open');
  const backdrop = document.getElementById('sb-backdrop');
  if (open) open.addEventListener('click', () => body.classList.add('nav-open'));
  if (backdrop) backdrop.addEventListener('click', () => body.classList.remove('nav-open'));

  // ---- toasts: auto-dismiss after 6 s (errors stay until closed)
  document.querySelectorAll('.toast-card').forEach((t) => {
    const close = () => { t.classList.add('is-leaving'); setTimeout(() => t.remove(), 250); };
    t.querySelector('.toast-x').addEventListener('click', close);
    if (!t.classList.contains('is-error')) setTimeout(close, 6000);
  });

  // ---- Refresh All: run in background, show live status, reload when done
  const btn = document.getElementById('refresh-btn');
  const info = document.getElementById('refresh-info');
  const form = document.getElementById('refresh-form');
  function busy() {
    btn.disabled = true;
    info.className = 'status-pill is-busy';
    info.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Refreshing…';
  }
  function poll() {
    fetch(NONGRN.refreshStatusUrl).then((r) => r.json()).then((s) => {
      if (s.running) { setTimeout(poll, 2500); return; }
      if (s.last && s.last.status === 'failed') {
        info.className = 'status-pill is-error';
        info.innerHTML = '<i class="bi bi-x-circle-fill"></i> Refresh failed';
        info.title = s.last.message;
        btn.disabled = false;
      } else location.reload();
    }).catch(() => setTimeout(poll, 4000));
  }
  if (form) form.addEventListener('submit', (e) => {
    e.preventDefault();
    busy();
    fetch(form.action, { method: 'POST', body: new FormData(form), headers: { 'X-Requested-With': 'fetch' } })
      .then(() => setTimeout(poll, 1500));
  });
  // the upload popup on Sources follows its own refresh
  if (NONGRN.refreshing && !document.getElementById('upload-modal')) setTimeout(poll, 2500);
})();
