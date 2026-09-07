(() => {
  const API = window.REELO_API || 'http://localhost:8000';
  const state = { open: false, loading: false };
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const fmt = n => { n = Number(n || 0); return n >= 1e6 ? (n/1e6).toFixed(1)+'M' : n >= 1e3 ? (n/1e3).toFixed(1)+'K' : String(n); };
  const headers = () => { const h = {}; const t = localStorage.getItem('reelo_token'); if (t) h.Authorization = 'Bearer ' + t; return h; };

  function mount() {
    if ($('trendingPanel')) return;
    const style = document.createElement('style');
    style.textContent = '.trending-panel{position:absolute;inset:0;background:#080808;z-index:25;display:none;padding:calc(18px + env(safe-area-inset-top)) 16px 24px;overflow:auto}.trending-panel.show{display:block}.trending-head{display:flex;align-items:center;gap:12px;margin-bottom:18px}.trending-head button{border:0;background:none;color:#fff;font-size:28px}.trend-sub{color:#888;margin:-8px 0 16px}.trend-card{display:block;padding:15px 0;border-bottom:1px solid #252525}.trend-rank{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:9px;background:#191919;font-weight:900;margin-right:10px}.trend-title{font-weight:800}.trend-meta{color:#888;font-size:12px;margin:6px 0 0 40px}.trend-empty{text-align:center;color:#777;padding:60px 10px}.discover-trending{border:1px solid #333;background:#171717;color:#fff;border-radius:12px;padding:12px 14px;width:100%;font-weight:800;margin-bottom:16px}';
    document.head.appendChild(style);
    const panel = document.createElement('section'); panel.id='trendingPanel'; panel.className='trending-panel';
    panel.innerHTML='<div class="trending-head"><button onclick="window.closeTrending()">‹</button><h2 style="margin:0">Trending</h2></div><p class="trend-sub">What people are watching right now</p><div id="trendingList" class="trend-empty">Loading…</div>';
    document.querySelector('.shell')?.appendChild(panel);
  }

  async function openTrending() {
    mount(); state.open=true; $('trendingPanel').classList.add('show'); $('trendingList').innerHTML='Loading…';
    try {
      const r = await fetch(API+'/api/trending?limit=50',{headers:headers()});
      if (!r.ok) throw Error('trending');
      const d = await r.json(); const items=d.items||[];
      $('trendingList').className=items.length?'':'trend-empty';
      $('trendingList').innerHTML=items.length ? items.map((v,i)=>`<button class="trend-card" style="width:100%;text-align:left;background:none;border:0;color:#fff" onclick="window.openTrendingVideo('${esc(v.id)}')"><span class="trend-rank">${i+1}</span><span class="trend-title">@${esc(v.username||'creator')}</span><div class="trend-meta">${fmt(v.views)} views · ${fmt(v.likes)} likes · ${fmt(v.comments)} comments</div></button>`).join('') : 'No trending videos yet.';
    } catch(e) { $('trendingList').className='trend-empty'; $('trendingList').textContent='Trending is temporarily unavailable.'; }
  }
  function closeTrending(){ const p=$('trendingPanel'); if(p)p.classList.remove('show'); state.open=false; }
  function openTrendingVideo(id){ closeTrending(); const card=document.querySelector(`.video-card[data-id="${CSS.escape(id)}"]`); if(card){card.scrollIntoView({behavior:'smooth'});return;} const v=(window.feedItems||[]).find(x=>String(x.id)===String(id)); if(v){ window.feedItems=[v].concat(window.feedItems||[]); if(typeof window.render==='function')window.render(); setTimeout(()=>document.querySelector(`.video-card[data-id="${CSS.escape(id)}"]`)?.scrollIntoView({behavior:'smooth'}),80); } }
  window.openTrending=openTrending; window.closeTrending=closeTrending; window.openTrendingVideo=openTrendingVideo;
  document.addEventListener('DOMContentLoaded',()=>{ mount(); const tabs=document.querySelector('.tabs'); if(tabs&&!$('trendingBtn')){ const b=document.createElement('button'); b.id='trendingBtn'; b.textContent='Trending'; b.onclick=openTrending; tabs.appendChild(b); } });
})();
