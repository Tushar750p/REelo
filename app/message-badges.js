(() => {
  const API = window.REELO_API || location.origin;
  const token = () => localStorage.getItem('reelo_token') || '';
  const headers = () => token() ? { Authorization: 'Bearer ' + token() } : {};

  function ensureBadge(el, id) {
    let b = el.querySelector('[data-reelo-badge="' + id + '"]');
    if (!b) {
      b = document.createElement('span');
      b.dataset.reeloBadge = id;
      b.style.cssText = 'position:absolute;top:2px;right:8px;min-width:17px;height:17px;padding:0 5px;border-radius:999px;background:#fff;color:#000;font:800 10px/17px system-ui;text-align:center;box-shadow:0 2px 10px #000;display:none;z-index:9;';
      if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
      el.appendChild(b);
    }
    return b;
  }

  function setBadge(el, id, count) {
    const b = ensureBadge(el, id);
    const n = Number(count) || 0;
    b.textContent = n > 99 ? '99+' : String(n);
    b.style.display = n ? 'block' : 'none';
    el.setAttribute('aria-label', (el.textContent || '').trim() + (n ? ', ' + n + ' unread' : ''));
  }

  async function refresh() {
    if (!token()) return;
    try {
      const [nr, mr] = await Promise.all([
        fetch(API + '/api/notifications?limit=1', { headers: headers() }),
        fetch(API + '/api/messages?limit=1', { headers: headers() })
      ]);
      if (!nr.ok && !mr.ok) return;
      const nd = nr.ok ? await nr.json() : {};
      const md = mr.ok ? await mr.json() : {};
      document.querySelectorAll('.bottom button').forEach(btn => {
        const text = (btn.textContent || '').trim().toLowerCase();
        if (text.startsWith('activity')) setBadge(btn, 'activity', nd.unread_count || 0);
      });
      const profileLinks = document.querySelectorAll('a[href="messages.html"],a[href="/messages.html"]');
      profileLinks.forEach(a => setBadge(a, 'messages', md.unread_count || 0));
    } catch (_) {}
  }

  function scan() {
    refresh();
  }
  scan();
  setInterval(scan, 10000);
})();
