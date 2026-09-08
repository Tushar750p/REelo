(function(){
  const CARD_SELECTOR='.video-card';
  const VIDEO_SELECTOR='video';
  const MUTE_KEY='reelo_feed_muted';
  let activeCard=null;
  let raf=0;

  function cards(){return Array.from(document.querySelectorAll(CARD_SELECTOR));}
  function videos(){return cards().map(c=>c.querySelector(VIDEO_SELECTOR)).filter(Boolean);}
  function isMuted(){return localStorage.getItem(MUTE_KEY)!=='0';}
  function setMuted(v){localStorage.setItem(MUTE_KEY,v?'1':'0');}
  function pauseAll(except){videos().forEach(v=>{if(v!==except&&!v.paused)v.pause()});}

  function setPreloadAround(card){
    const list=cards(),i=list.indexOf(card);
    list.forEach((c,n)=>{
      const v=c.querySelector(VIDEO_SELECTOR);
      if(!v)return;
      v.preload=(Math.abs(n-i)<=1)?'auto':'metadata';
    });
  }

  function updateMuteUI(card,muted){
    if(!card)return;
    let badge=card.querySelector('.reelo-mute-badge');
    if(!badge){
      badge=document.createElement('button');
      badge.type='button';
      badge.className='reelo-mute-badge';
      badge.setAttribute('aria-label','Toggle sound');
      badge.style.cssText='position:absolute;right:16px;top:72px;z-index:6;width:40px;height:40px;border:1px solid #ffffff33;border-radius:50%;background:#0008;color:#fff;font-size:18px;backdrop-filter:blur(6px);cursor:pointer';
      badge.addEventListener('click',function(e){e.preventDefault();e.stopPropagation();toggleMute(card);});
      card.appendChild(badge);
    }
    badge.textContent=muted?'🔇':'🔊';
  }

  function activate(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(!video)return;
    activeCard=card;
    pauseAll(video);
    setPreloadAround(card);
    video.setAttribute('playsinline','');
    video.playsInline=true;
    video.muted=isMuted();
    updateMuteUI(card,video.muted);
    const p=video.play();
    if(p&&typeof p.catch==='function')p.catch(()=>{});
  }

  function deactivate(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(video)video.pause();
    if(activeCard===card)activeCard=null;
  }

  function toggleMute(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(!video)return;
    const muted=!video.muted;
    video.muted=muted;
    setMuted(muted);
    updateMuteUI(card,muted);
    if(!muted){
      const p=video.play();
      if(p&&p.catch)p.catch(()=>{});
    }
  }

  function observeCard(card){
    if(card.dataset.reeloPlaybackObserved==='1')return;
    card.dataset.reeloPlaybackObserved='1';
    observer.observe(card);
  }

  const observer=new IntersectionObserver(entries=>{
    entries.forEach(entry=>{
      if(entry.isIntersecting&&entry.intersectionRatio>=0.68)activate(entry.target);
      else if(!entry.isIntersecting||entry.intersectionRatio<0.25)deactivate(entry.target);
    });
  },{threshold:[0.25,0.68,0.9]});

  function scan(){cards().forEach(observeCard);}
  function scheduleScan(){if(raf)return;raf=requestAnimationFrame(()=>{raf=0;scan()});}

  scan();
  const root=document.getElementById('feed')||document.querySelector('.feed')||document.body;
  root.addEventListener('scroll',scheduleScan,{passive:true});
  new MutationObserver(scheduleScan).observe(root,{childList:true,subtree:true});

  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){pauseAll(null);return;}
    if(activeCard)activate(activeCard);
  });

  window.addEventListener('pagehide',()=>pauseAll(null));
})();
