(() => {
  const input = document.getElementById('q');
  const content = document.getElementById('content');
  if (!input || !content) return;
  const API = window.REELO_API || 'http://localhost:8000';
  let timer = null;
  let lastQuery = '';
  const esc = s => String(s ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const fmt = n => { n=Number(n||0); return n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':String(n); };
  const videoUrl = v => v.filename?.startsWith('http') ? v.filename : API+(v.filename?.startsWith('/')?'':'/')+v.filename;

  if (!document.getElementById('smart-search-style')) {
    const style=document.createElement('style'); style.id='smart-search-style'; style.textContent=`
      .smart-suggest{margin:10px 0 4px;padding:8px 0;border-bottom:1px solid #222}
      .smart-label{font-size:11px;color:#777;text-transform:uppercase;letter-spacing:.08em;margin:4px 0 8px}
      .smart-chip{display:inline-block;border:1px solid #333;background:#151515;color:#ddd;border-radius:18px;padding:7px 11px;margin:0 6px 6px 0;cursor:pointer}
      .smart-chip:hover{background:#222}
      .smart-topics{display:flex;gap:7px;overflow:auto;padding-bottom:4px}
      .smart-topic{flex:none;border:1px solid #333;border-radius:16px;padding:6px 10px;color:#aaa;font-size:12px}
      .smart-video{cursor:pointer;transition:background .15s;border-radius:10px;padding:10px;margin:0 -8px}
      .smart-video:hover{background:#151515}
      .smart-badge{font-size:10px;color:#888;margin-top:5px}
    `; document.head.appendChild(style);
  }

  function render(data) {
    const items=data.items||[], suggestions=data.suggestions||[], topics=data.topics||[], trends=data.trending_topics||[];
    let html='';
    if (suggestions.length) html += `<div class="smart-suggest"><div class="smart-label">Suggestions</div>${suggestions.map(s=>`<button class="smart-chip" data-suggestion="${esc(s)}">${esc(s)}</button>`).join('')}</div>`;
    if (topics.length || trends.length) html += `<div class="smart-suggest"><div class="smart-label">Explore topics</div><div class="smart-topics">${[...new Set([...topics,...trends])].slice(0,8).map(t=>`<button class="smart-topic" data-topic="${esc(t)}">${esc(t)}</button>`).join('')}</div></div>`;
    if (items.length) html += `<div class="section-title">Smart results</div>` + items.map((v,i)=>`<article class="video smart-video" data-video-id="${esc(v.id)}"><video class="thumb" src="${esc(videoUrl(v))}" muted playsinline preload="metadata"></video><div class="meta"><div class="name">@${esc(v.username||'creator')}</div><div class="caption">${esc(v.caption||'No caption')}</div><div class="stats">${fmt(v.likes)} likes · ${fmt(v.comments)} comments · ${fmt(v.views)} views</div><div class="smart-badge">${i<3?'Top match · ':''}${data.personalized?'Personalized ranking':''}</div></div></article>`).join('');
    content.innerHTML=html || '<div class="empty">No smart results found. Try a creator, topic, or hashtag.</div>';
    content.querySelectorAll('[data-suggestion]').forEach(b=>b.onclick=()=>{input.value=b.dataset.suggestion; lastQuery=''; run(input.value);});
    content.querySelectorAll('[data-topic]').forEach(b=>b.onclick=()=>{input.value=b.dataset.topic; lastQuery=''; run(input.value);});
  }

  async function run(value) {
    const query=value.trim();
    if (!query || query===lastQuery) return;
    lastQuery=query;
    content.innerHTML='<div class="loading">Finding the best matches…</div>';
    try {
      const r=await fetch(API+'/api/smart-search?q='+encodeURIComponent(query)+'&limit=30');
      if(!r.ok) throw new Error('search');
      render(await r.json());
    } catch(e) { content.innerHTML='<div class="empty">Smart search is temporarily unavailable.</div>'; }
  }

  // Capture before the legacy search handler so Smart Search is the single renderer.
  input.addEventListener('input', event => {
    event.stopImmediatePropagation();
    clearTimeout(timer);
    lastQuery='';
    timer=setTimeout(()=>run(input.value),220);
  }, true);
})();
