(function(){
  const API=window.REELO_API||'http://localhost:8000';
  const following=new Set(JSON.parse(localStorage.getItem('reelo_following')||'[]').map(String));
  const save=()=>localStorage.setItem('reelo_following',JSON.stringify([...following]));
  const token=()=>localStorage.getItem('reelo_token')||'';
  const findVideo=card=>{const id=card?.getAttribute('data-id');return id&&Array.isArray(window.feedItems)?window.feedItems.find(v=>String(v.id)===String(id)):null};
  const findCreator=card=>{const v=findVideo(card);return v?.user_id?String(v.user_id):null};
  const toast=msg=>{if(typeof window.toast==='function')window.toast(msg);};
  function paint(card){
    const btn=card?.querySelector('.follow'); if(!btn)return;
    const uid=findCreator(card); if(!uid)return;
    const self=typeof window.me!=='undefined'&&window.me&&String(window.me.id||window.me.user?.id)===uid;
    if(self){btn.style.display='none';return;}
    const active=following.has(uid);
    btn.textContent=active?'Following':'Follow';
    btn.setAttribute('aria-pressed',active?'true':'false');
    btn.classList.toggle('is-following',active);
  }
  function scan(){document.querySelectorAll('.video-card').forEach(paint)}
  async function toggle(card){
    const uid=findCreator(card); if(!uid)return;
    const t=token(); if(!t){if(typeof window.openAuth==='function')window.openAuth('login');return;}
    const btn=card.querySelector('.follow'); if(btn)btn.disabled=true;
    try{
      const r=await fetch(API+'/api/users/'+encodeURIComponent(uid)+'/follow',{method:'POST',headers:{Authorization:'Bearer '+t}});
      const d=await r.json().catch(()=>({}));
      if(!r.ok)throw Error(d.detail||'Could not update follow status');
      if(d.action==='follow')following.add(uid);else following.delete(uid);
      save(); paint(card);
      toast(d.action==='follow'?'Following @'+(findVideo(card)?.username||'creator'):'Unfollowed @'+(findVideo(card)?.username||'creator'));
    }catch(e){toast(e.message||'Could not update follow status');}
    finally{if(btn)btn.disabled=false;}
  }
  document.addEventListener('click',e=>{
    const btn=e.target.closest('.follow'); if(!btn)return;
    const card=btn.closest('.video-card'); if(!card)return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation(); toggle(card);
  },true);
  new MutationObserver(scan).observe(document.getElementById('feed')||document.body,{childList:true,subtree:true});
  window.addEventListener('load',scan); setInterval(scan,1500);
})();
