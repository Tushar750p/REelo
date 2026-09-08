(function(){
  const root=document.getElementById('feed')||document.querySelector('.feed');
  if(!root)return;
  const likeCooldown=new WeakMap();
  function cardFromTarget(t){return t&&t.closest?t.closest('.video-card'):null;}
  function likeCard(card){
    if(!card||likeCooldown.has(card))return;
    const btn=card.querySelector('[aria-label*="like" i],.like-btn,[data-action="like"]');
    if(btn){btn.click();}
    else{card.dispatchEvent(new CustomEvent('reelo:doubletap-like',{bubbles:true}));}
    likeCooldown.set(card,1);setTimeout(()=>likeCooldown.delete(card),420);
    const heart=document.createElement('div');heart.className='reelo-heart-pop';heart.textContent='♥';card.appendChild(heart);setTimeout(()=>heart.remove(),720);
  }
  function enhance(card){
    if(card.dataset.reeloPolish==='1')return;
    card.dataset.reeloPolish='1';
    const video=card.querySelector('video');
    if(!video)return;
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
  const style=document.createElement('style');style.textContent='.reelo-progress{position:absolute;left:0;right:0;bottom:72px;height:2px;background:#ffffff35;z-index:9;pointer-events:none}.reelo-progress i{display:block;height:100%;width:100%;background:#fff;transform:scaleX(0);transform-origin:left center;box-shadow:0 0 8px #fff8}.reelo-heart-pop{position:absolute;left:50%;top:50%;z-index:15;transform:translate(-50%,-50%) scale(.35);font-size:108px;line-height:1;color:#fff;text-shadow:0 4px 30px #0008;pointer-events:none;animation:reeloHeart .68s cubic-bezier(.2,.8,.2,1) forwards}@keyframes reeloHeart{0%{opacity:0;transform:translate(-50%,-50%) scale(.25) rotate(-12deg)}18%{opacity:1}62%{opacity:1;transform:translate(-50%,-50%) scale(1.08) rotate(0)}100%{opacity:0;transform:translate(-50%,-50%) scale(1.3) rotate(6deg)}}';document.head.appendChild(style);
  scan();new MutationObserver(scan).observe(root,{childList:true,subtree:true});
})();