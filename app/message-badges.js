(() => {
  const API = window.REELO_API || location.origin;
  const token = () => localStorage.getItem('reelo_token') || '';
  const headers = () => token() ? { Authorization: 'Bearer ' + token() } : {};

  function ensureBadge(el, id) {
    let b = el.querySelector('[data-reelo-badge="' + id + '"]');
    if (!b) {
      b = document.createElement('span');
      b.dataset.reeloBadge = id;
      b.style.cssText = 'position:absolute;top:1px;right:5px;min-width:16px;height:16px;padding:0 4px;border-radius:999px;background:#fff;color:#000;font:800 9px/16px system-ui;text-align:center;box-shadow:0 2px 10px #000;display:none;z-index:9;';
      if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
      el.appendChild(b);
    }
    return b;
  }

  function setBadge(el, id, count) {
    if (!el) return;
    const b = ensureBadge(el, id);
    const n = Number(count) || 0;
    b.textContent = n > 99 ? '99+' : String(n);
    b.style.display = n ? 'block' : 'none';
  }

  function addInboxButton() {
    const nav = document.querySelector('.bottom');
    if (!nav || nav.querySelector('[data-reelo-inbox]')) return;
    const activity = [...nav.querySelectorAll('button')].find(b => (b.textContent || '').trim().toLowerCase().startsWith('activity'));
    if (!activity) return;
    const b = document.createElement('button');
    b.dataset.reeloInbox = '1';
    b.innerHTML = '<span class="icon">✉</span>Messages';
    b.onclick = () => { location.href = 'messages.html'; };
    nav.insertBefore(b, activity);
  }

  async function refresh() {
    addInboxButton();
    if (!token()) return;
    try {
      const [nr, mr, rr] = await Promise.all([
        fetch(API + '/api/notifications/summary', { headers: headers() }),
        fetch(API + '/api/messages/unread/summary', { headers: headers() }),
        fetch(API + '/api/message-requests/summary', { headers: headers() })
      ]);
      const nd = nr.ok ? await nr.json() : {};
      const md = mr.ok ? await mr.json() : {};
      const rd = rr.ok ? await rr.json() : {};
      const activity = [...document.querySelectorAll('.bottom button')].find(b => (b.textContent || '').trim().toLowerCase().startsWith('activity'));
      const inbox = document.querySelector('[data-reelo-inbox]');
      const totalMessages = (Number(md.total_unread) || 0) + (Number(rd.incoming) || 0);
      setBadge(activity, 'activity', nd.unread || 0);
      setBadge(inbox, 'messages', totalMessages);
      document.querySelectorAll('#message').forEach(b => setBadge(b, 'profile-message', totalMessages));
    } catch (_) {}
  }

  refresh();
  setInterval(refresh, 10000);
})();
