/* REelo Save — production save integration */
(function(){
  const API = window.REELO_API || 'https://reelo-api-ko9x.onrender.com';
  let savedIds = new Set();

  function token(){ return localStorage.getItem('reelo_token') || ''; }
  function authHeaders(){
    const t = token();
    return t ? { Authorization: 'Bearer ' + t } : {};
  }
  function toastSafe(message){
    if (typeof window.toast === 'function') window.toast(message);
    else console.log('[REelo]', message);
  }

  function buttonId(btn){
    const text = btn && btn.getAttribute('onclick') || '';
    const m = text.match(/saveVideo\(['\"]([^'\"]+)/);
    return m ? m[1] : null;
  }

  function paint(btn, id){
    if (!btn || !id) return;
    const saved = savedIds.has(id);
    btn.dataset.saved = saved ? '1' : '0';
    const small = btn.querySelector('small');
    if (small) small.textContent = saved ? 'Saved' : 'Save';
    const icon = Array.from(btn.childNodes).find(n => n.nodeType === 3 && n.textContent.trim());
    if (icon) icon.textContent = saved ? '🔖' : '🔖';
    btn.setAttribute('aria-label', saved ? 'Remove from saved' : 'Save video');
    btn.title = saved ? 'Remove from saved' : 'Save video';
  }

  function paintAll(){
    document.querySelectorAll('.act').forEach(btn => {
      const id = buttonId(btn);
      if (id) paint(btn, id);
    });
  }

  async function loadSaved(){
    savedIds = new Set();
    if (!token()) { paintAll(); return; }
    try {
      const r = await fetch(API + '/api/saved?limit=100', { headers: authHeaders() });
      if (!r.ok) return;
      const data = await r.json();
      savedIds = new Set((data.items || []).map(v => String(v.id)));
      paintAll();
    } catch(e) { console.warn('REelo saved state unavailable', e); }
  }

  window.saveVideo = async function(videoId, btn){
    if (!token()) {
      toastSafe('Login required to save videos.');
      if (typeof window.openAuth === 'function') window.openAuth();
      return;
    }
    if (!btn) btn = document.querySelector('[onclick*="saveVideo(\'' + videoId + '\'"]');
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(API + '/api/videos/' + encodeURIComponent(videoId) + '/save', {
        method: 'POST', headers: authHeaders()
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || 'Could not save video');
      if (data.saved) savedIds.add(String(videoId));
      else savedIds.delete(String(videoId));
      paintAll();
      toastSafe(data.saved ? 'Video saved.' : 'Removed from Saved.');
    } catch(e) {
      toastSafe(e.message || 'Could not update Saved.');
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  window.addEventListener('load', loadSaved);
  window.addEventListener('storage', loadSaved);
  const feed = document.getElementById('feed');
  if (feed) new MutationObserver(paintAll).observe(feed, {childList:true, subtree:true});
  setTimeout(loadSaved, 1200);
})();
