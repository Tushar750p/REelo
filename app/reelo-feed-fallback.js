/* REelo Feed Fallback v2 - persistent media aware */
(function(){
  'use strict';
  const API=window.REELO_API||'https://reelo-api-ko9x.onrender.com';
  const demos=[
    {id:'demo-1',username:'reelo_creator',display_name:'REelo Creator',caption:'Build your vibe. Share your story. 🚀',filename:'https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4',likes:12400,comments:321,views:85000},
    {id:'demo-2',username:'futuredaily',display_name:'Future Daily',caption:'Create something people remember.',filename:'https://www.w3schools.com/html/mov_bbb.mp4',likes:8700,comments:142,views:54000}
  ];
  const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const mediaUrl=v=>{const u=v.storage_url||v.url||v.filename||'';return /^https?:\/\//i.test(u)?u:(u.startsWith('/media/')?API+u:API+'/media/'+u.replace(/^\//,''));};
  function render(items){
    const feed=document.getElementById('feed'); if(!feed||feed.querySelector('.video-card')) return;
    feed.innerHTML=items.map(v=>`<article class="video-card" data-video-id="${esc(v.id)}">
      <video src="${esc(mediaUrl(v))}" playsinline loop muted preload="metadata"></video>
      <div class="gradient"></div>
      <div class="info"><div class="creator"><div class="avatar">${esc((v.display_name||v.username||'R')[0]).toUpperCase()}</div><span class="handle">@${esc(v.username||'reelo')}</span><button class="follow" onclick="followUser('${esc(v.username||'')}')">Follow</button></div><div class="caption">${esc(v.caption||'')}</div><div class="sound">♫ Original sound</div></div>
      <div class="actions">
        <button class="act" onclick="likeVideo('${esc(v.id)}',this)">♡<small>${Number(v.likes||0)}</small></button>
        <button class="act" onclick="openComments('${esc(v.id)}')">💬<small>${Number(v.comments||0)}</small></button>
        <button class="act" onclick="shareVideo('${esc(v.id)}')">↗<small>Share</small></button>
        <button class="act" onclick="saveVideo('${esc(v.id)}',this)">🔖<small>Save</small></button>
        <button class="act more" onclick="openReport('${esc(v.id)}')">⋯</button>
      </div>
    </article>`).join('');
    feed.querySelectorAll('video').forEach(v=>{
      v.addEventListener('error',()=>{v.parentElement.classList.add('video-unavailable');});
      const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){v.play().catch(()=>{});}else v.pause();}),{threshold:.65}); io.observe(v);
      v.addEventListener('click',()=>v.paused?v.play().catch(()=>{}):v.pause());
    });
    if(window.REeloEnhanceFeed) window.REeloEnhanceFeed();
  }
  async function load(){
    const feed=document.getElementById('feed'); if(!feed) return;
    if(feed.querySelector('.video-card')) return;
    let items=[];
    try{
      const r=await fetch(API+'/api/feed?limit=20',{headers:localStorage.getItem('reelo_token')?{Authorization:'Bearer '+localStorage.getItem('reelo_token')}:{} });
      if(r.ok){const d=await r.json(); items=Array.isArray(d)?d:(d.items||d.videos||d.feed||[]);}
    }catch(e){}
    if(items.length) render(items); else render(demos);
  }
  window.addEventListener('load',()=>setTimeout(load,700));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden) setTimeout(load,250);});
})();