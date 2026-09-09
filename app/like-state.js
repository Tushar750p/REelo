(function(){
  const API=window.REELO_API||location.origin;
  const token=()=>localStorage.getItem('reelo_token')||'';
  const headers=()=>{const t=token();return t?{Authorization:'Bearer '+t}:{};};
  const fmt=n=>{n=Number(n||0);return n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':String(n)};
  function id(card){return card?.dataset?.id||card?.getAttribute('data-id')||'';}
  function paint(card,liked,likes){
    const btn=card?.querySelector('.actions button[onclick*="likeVideo"]');
    if(!btn)return;
    btn.innerHTML=(liked?'♥':'♡')+'<small>'+fmt(likes)+'</small>';
    btn.setAttribute('aria-label',liked?'Unlike video':'Like video');
    btn.classList.toggle('is-liked',!!liked);
  }
  async function syncCard(card){
    const t=token(),vid=id(card);if(!t||!vid)return;
    try{
      const r=await fetch(API+'/api/videos/'+encodeURIComponent(vid)+'/like/state',{headers:headers()});
      if(!r.ok)return;
      const d=await r.json();paint(card,d.liked,d.likes);
    }catch(_){ }
  }
  function scan(){document.querySelectorAll('.video-card').forEach(syncCard);}
  document.addEventListener('dblclick',function(e){
    const card=e.target.closest('.video-card');
    if(!card||e.target.closest('button,a,input,textarea'))return;
    const btn=card.querySelector('.actions button[onclick*="likeVideo"]');
    if(!btn)return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
    btn.click();
  },true);
  document.addEventListener('click',function(e){
    const btn=e.target.closest('.actions button[onclick*="likeVideo"]');
    if(!btn)return;
    const card=btn.closest('.video-card');
    if(!card)return;
    setTimeout(()=>syncCard(card),180);
  },true);
  scan();
  new MutationObserver(scan).observe(document.getElementById('feed')||document.body,{childList:true,subtree:true});
})();
