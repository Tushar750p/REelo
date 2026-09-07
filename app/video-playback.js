(function(){
  const CARD_SELECTOR='.video-card';
  const VIDEO_SELECTOR='video';
  const activeByCard=new WeakMap();
  let activeCard=null;
  let raf=0;

  function cards(){return Array.from(document.querySelectorAll(CARD_SELECTOR));}
  function videos(){return cards().map(c=>c.querySelector(VIDEO_SELECTOR)).filter(Boolean);}
  function pauseAll(except){videos().forEach(v=>{if(v!==except&&!v.paused)v.pause()});}

  function setPreloadAround(card){
    const list=cards(),i=list.indexOf(card);
    list.forEach((c,n)=>{const v=c.querySelector(VIDEO_SELECTOR);if(!v)return;v.preload=(Math.abs(n-i)<=1)?'auto':'metadata'});
  }

  function activate(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(!video)return;
    if(activeCard===card&&activeByCard.get(card))return;
    activeCard=card;activeByCard.set(card,true);
    pauseAll(video);
    setPreloadAround(card);
    video.preload='auto';
    const p=video.play();
    if(p&&typeof p.catch==='function')p.catch(()=>{});
  }

  function deactivate(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(video)video.pause();
    activeByCard.set(card,false);
    if(activeCard===card)activeCard=null;
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
  function scheduleScan(){if(raf)return;raf=requestAnimationFrame(()=>{raf=0;scan()})}

  scan();
  const root=document.getElementById('feed')||document.querySelector('.feed')||document.body;
  root.addEventListener('scroll',scheduleScan,{passive:true});
  new MutationObserver(scheduleScan).observe(root,{childList:true,subtree:true});

  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){pauseAll(null);return;}
    if(activeCard){const v=activeCard.querySelector(VIDEO_SELECTOR);if(v){const p=v.play();if(p&&p.catch)p.catch(()=>{})}}
  });

  window.addEventListener('pagehide',()=>pauseAll(null));
})();
