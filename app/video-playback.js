(function(){
  const CARD_SELECTOR='.video-card';
  const VIDEO_SELECTOR='video';
  const MUTE_KEY='reelo_feed_muted';
  let activeCard=null;
  let raf=0;
  let tapTimer=null;

  function cards(){return Array.from(document.querySelectorAll(CARD_SELECTOR));}
  function videos(){return cards().map(c=>c.querySelector(VIDEO_SELECTOR)).filter(Boolean);}
  function isMuted(){return localStorage.getItem(MUTE_KEY)!=='0';}
  function setMuted(v){localStorage.setItem(MUTE_KEY,v?'1':'0');}
  function pauseAll(except){videos().forEach(v=>{if(v!==except&&!v.paused)v.pause()});}

  function ensurePlaybackUI(card){
    if(!card)return;
    if(!card.querySelector('.reelo-progress')){
      const wrap=document.createElement('div');
      wrap.className='reelo-progress';
      wrap.innerHTML='<div class="reelo-progress-fill"></div>';
      wrap.style.cssText='position:absolute;left:0;right:0;bottom:64px;height:3px;background:#ffffff35;z-index:6;pointer-events:none;overflow:hidden';
      wrap.firstElementChild.style.cssText='height:100%;width:0;background:#fff;transform-origin:left center;transition:width .08s linear';
      card.appendChild(wrap);
    }
    if(!card.querySelector('.reelo-buffer')){
      const b=document.createElement('div');
      b.className='reelo-buffer';
      b.textContent='';
      b.style.cssText='position:absolute;left:50%;top:50%;width:34px;height:34px;margin:-17px;border:3px solid #ffffff55;border-top-color:#fff;border-radius:50%;z-index:7;display:none;animation:reeloSpin .8s linear infinite;pointer-events:none';
      card.appendChild(b);
    }
    if(!document.getElementById('reeloPlaybackStyle')){
      const s=document.createElement('style');
      s.id='reeloPlaybackStyle';
      s.textContent='@keyframes reeloSpin{to{transform:rotate(360deg)}}@keyframes reeloTap{0%{transform:translate(-50%,-50%) scale(.55);opacity:0}20%{opacity:1}70%{transform:translate(-50%,-50%) scale(1.12);opacity:1}100%{transform:translate(-50%,-50%) scale(1.35);opacity:0}}.reelo-heart{position:absolute;left:50%;top:50%;z-index:8;font-size:92px;line-height:1;transform:translate(-50%,-50%);pointer-events:none;animation:reeloTap .65s ease-out forwards;text-shadow:0 4px 18px #0008}.reelo-paused:after{content:"▶";position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:58px;height:58px;border-radius:50%;display:grid;place-items:center;background:#0008;border:1px solid #fff4;color:#fff;font-size:23px;z-index:6;pointer-events:none}';
      document.head.appendChild(s);
    }
  }

  function updateProgress(card){
    const v=card?.querySelector(VIDEO_SELECTOR),fill=card?.querySelector('.reelo-progress-fill');
    if(!v||!fill)return;
    const pct=v.duration>0?Math.min(100,(v.currentTime/v.duration)*100):0;
    fill.style.width=pct+'%';
  }

  function updateBuffer(card){
    const v=card?.querySelector(VIDEO_SELECTOR),b=card?.querySelector('.reelo-buffer');
    if(!v||!b)return;
    b.style.display=(!v.paused&&!v.ended&&v.readyState<3)?'block':'none';
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

  function showHeart(card){
    const old=card.querySelector('.reelo-heart');
    if(old)old.remove();
    const h=document.createElement('div');
    h.className='reelo-heart';
    h.textContent='♥';
    card.appendChild(h);
    setTimeout(()=>h.remove(),700);
  }

  function togglePlay(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(!video)return;
    if(video.paused){
      video.classList.remove('reelo-paused');
      const p=video.play();if(p&&p.catch)p.catch(()=>{});
    }else{
      video.pause();
      video.classList.add('reelo-paused');
    }
  }

  function bindVideo(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(!video||video.dataset.reeloEvents==='1')return;
    video.dataset.reeloEvents='1';
    ['timeupdate','durationchange','progress','loadedmetadata'].forEach(ev=>video.addEventListener(ev,()=>updateProgress(card)));
    ['waiting','stalled'].forEach(ev=>video.addEventListener(ev,()=>updateBuffer(card)));
    ['playing','canplay','ended'].forEach(ev=>video.addEventListener(ev,()=>{updateBuffer(card);if(ev==='ended')video.classList.remove('reelo-paused')}));
    video.addEventListener('click',function(e){
      if(e.detail>1)return;
      clearTimeout(tapTimer);
      tapTimer=setTimeout(()=>{togglePlay(card);tapTimer=null},190);
    });
    video.addEventListener('dblclick',function(e){
      e.preventDefault();
      clearTimeout(tapTimer);tapTimer=null;
      showHeart(card);
    });
  }

  function activate(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(!video)return;
    activeCard=card;
    ensurePlaybackUI(card);
    bindVideo(card);
    pauseAll(video);
    setPreloadAround(card);
    video.setAttribute('playsinline','');
    video.playsInline=true;
    video.muted=isMuted();
    video.classList.remove('reelo-paused');
    updateMuteUI(card,video.muted);
    updateProgress(card);
    updateBuffer(card);
    const p=video.play();
    if(p&&typeof p.catch==='function')p.catch(()=>{});
  }

  function deactivate(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(video){video.pause();video.classList.remove('reelo-paused');updateBuffer(card)}
    if(activeCard===card)activeCard=null;
  }

  function toggleMute(card){
    const video=card?.querySelector(VIDEO_SELECTOR);
    if(!video)return;
    const muted=!video.muted;
    video.muted=muted;
    setMuted(muted);
    updateMuteUI(card,muted);
    if(!muted){const p=video.play();if(p&&p.catch)p.catch(()=>{})}
  }

  function setPreloadAround(card){
    const list=cards(),i=list.indexOf(card);
    list.forEach((c,n)=>{
      const v=c.querySelector(VIDEO_SELECTOR);
      if(!v)return;
      v.preload=(Math.abs(n-i)<=1)?'auto':'metadata';
    });
  }

  function observeCard(card){
    if(card.dataset.reeloPlaybackObserved==='1')return;
    card.dataset.reeloPlaybackObserved='1';
    ensurePlaybackUI(card);
    bindVideo(card);
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
    if(document.hidden){pauseAll(null);return}
    if(activeCard)activate(activeCard);
  });
  window.addEventListener('pagehide',()=>pauseAll(null));
})();
