(function(){
  const root=document.getElementById('feed')||document.querySelector('.feed');
  if(!root)return;
  const API=window.REELO_API||'http://localhost:8000';
  const likeCooldown=new WeakMap();
  const saveState=new Map();
  const $=(sel,scope=document)=>scope.querySelector(sel);
  function headers(){const t=localStorage.getItem('reelo_token')||'';return t?{Authorization:'Bearer '+t}:{};}
  function toast(msg){if(typeof window.toast==='function'){window.toast(msg);return}const el=document.getElementById('toast');if(!el)return;el.textContent=msg;el.style.display='block';clearTimeout(el._t);el._t=setTimeout(()=>el.style.display='none',2200);}
  function cardFromTarget(t){return t&&t.closest?t.closest('.video-card'):null;}
  function videoId(card){return card?.dataset?.id||card?.getAttribute('data-id')||card?.dataset?.videoId||card?.getAttribute('data-video-id');}
  function likeCard(card){
    if(!card||likeCooldown.has(card))return;
    const btn=card.querySelector('[aria-label*="like" i],.like-btn,[data-action="like"]');
    if(btn){btn.click();}
    else{card.dispatchEvent(new CustomEvent('reelo:doubletap-like',{bubbles:true}));}
    likeCooldown.set(card,1);setTimeout(()=>likeCooldown.delete(card),420);
    const heart=document.createElement('div');heart.className='reelo-heart-pop';heart.textContent='♥';card.appendChild(heart);setTimeout(()=>heart.remove(),720);
  }
  async function loadSaveState(card,id,btn){
    const t=localStorage.getItem('reelo_token')||'';
    if(!t||!id)return;
    try{const r=await fetch(API+'/api/saves/video/'+encodeURIComponent(id),{headers:headers()});if(!r.ok)return;const d=await r.json();saveState.set(String(id),!!d.saved);setSaveButton(btn,!!d.saved);}catch(e){}
  }
  function setSaveButton(btn,saved){
    btn.setAttribute('aria-label',saved?'Unsave video':'Save video');
    btn.title=saved?'Remove from saved':'Save video';
    btn.querySelector('.reelo-action-icon').textContent=saved?'🔖':'🔖';
    btn.classList.toggle('is-saved',saved);
    const label=btn.querySelector('small');if(label)label.textContent=saved?'Saved':'Save';
  }
  async function toggleSave(card,btn){
    const id=videoId(card);if(!id)return;
    const t=localStorage.getItem('reelo_token')||'';
    if(!t){if(typeof window.openAuth==='function')window.openAuth('login');else toast('Log in to save videos');return;}
    const previous=saveState.get(String(id))===true;
    setSaveButton(btn,!previous);saveState.set(String(id),!previous);btn.disabled=true;
    try{
      const r=await fetch(API+'/api/saves/video/'+encodeURIComponent(id),{method:previous?'DELETE':'POST',headers:headers()});
      if(!r.ok){const d=await r.json().catch(()=>({}));throw Error(d.detail||'Could not update saved video');}
      toast(previous?'Removed from Saved':'Saved to your collection');
    }catch(e){saveState.set(String(id),previous);setSaveButton(btn,previous);toast(e.message||'Could not update Saved');}
    finally{btn.disabled=false;}
  }
  async function shareCard(card){
    const id=videoId(card);if(!id)return;
    const url=new URL(location.href);url.search='';url.hash='';url.searchParams.set('video',id);
    const data={title:'REelo video',text:'Watch this on REelo',url:url.href};
    try{
      if(navigator.share)await navigator.share(data);
      else{await navigator.clipboard.writeText(url.href);toast('Video link copied');}
    }catch(e){if(e?.name!=='AbortError')toast('Could not share video');}
  }
  function ensureActions(card){
    const actions=card.querySelector('.actions');if(!actions)return;
    const id=videoId(card);if(!id)return;
    let save=actions.querySelector('.reelo-save-action');
    if(!save){save=document.createElement('button');save.type='button';save.className='act reelo-save-action';save.innerHTML='<span class="reelo-action-icon">🔖</span><small>Save</small>';actions.insertBefore(save,actions.querySelector('.more')||null);save.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();toggleSave(card,save)});}
    let share=actions.querySelector('.reelo-share-action');
    if(!share){share=document.createElement('button');share.type='button';share.className='act reelo-share-action';share.innerHTML='<span class="reelo-action-icon">↗</span><small>Share</small>';actions.insertBefore(share,actions.querySelector('.more')||null);share.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();shareCard(card)});}
    loadSaveState(card,id,save);
  }
  function enhance(card){
    if(!card)return;
    ensureActions(card);
    if(card.dataset.reeloPolish==='1')return;
    card.dataset.reeloPolish='1';
    const video=card.querySelector('video');if(!video)return;
    const progress=document.createElement('div');progress.className='reelo-progress';progress.innerHTML='<i></i>';card.appendChild(progress);
    video.addEventListener('timeupdate',()=>{if(video.duration)progress.firstElementChild.style.transform='scaleX('+Math.min(1,video.currentTime/video.duration)+')'});
    video.addEventListener('ended',()=>{progress.firstElementChild.style.transform='scaleX(0)'});
    let lastTap=0;
    card.addEventListener('pointerup',e=>{
      if(e.target.closest('button,a,input,textarea'))return;
      const now=Date.now();
      if(now-lastTap<320){e.preventDefault();likeCard(card);lastTap=0;return;}
      lastTap=now;
      setTimeout(()=>{if(Date.now()-lastTap>=300){if(video.paused){video.play().catch(()=>{});}else video.pause();}},310);
    });
  }
  function scan(){root.querySelectorAll('.video-card').forEach(enhance)}
  const style=document.createElement('style');style.textContent='.reelo-progress{position:absolute;left:0;right:0;bottom:72px;height:2px;background:#ffffff35;z-index:9;pointer-events:none}.reelo-progress i{display:block;height:100%;width:100%;background:#fff;transform:scaleX(0);transform-origin:left center;box-shadow:0 0 8px #fff8}.reelo-heart-pop{position:absolute;left:50%;top:50%;z-index:15;transform:translate(-50%,-50%) scale(.35);font-size:108px;line-height:1;color:#fff;text-shadow:0 4px 30px #0008;pointer-events:none;animation:reeloHeart .68s cubic-bezier(.2,.8,.2,1) forwards}@keyframes reeloHeart{0%{opacity:0;transform:translate(-50%,-50%) scale(.25) rotate(-12deg)}18%{opacity:1}62%{opacity:1;transform:translate(-50%,-50%) scale(1.08) rotate(0)}100%{opacity:0;transform:translate(-50%,-50%) scale(1.3) rotate(6deg)}}.reelo-save-action,.reelo-share-action{transition:transform .16s ease,opacity .16s ease}.reelo-save-action.is-saved{filter:drop-shadow(0 0 7px #fff6)}.reelo-save-action:active,.reelo-share-action:active{transform:scale(.9)}.reelo-save-action:disabled{opacity:.6}';document.head.appendChild(style);
  scan();new MutationObserver(scan).observe(root,{childList:true,subtree:true});
})();