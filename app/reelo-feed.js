/* REelo Feed Interactions v2 */
(function(){
  'use strict';

  function enhanceCard(card){
    if(!card || card.dataset.reeloEnhanced) return;
    const video=card.querySelector('video');
    if(!video) return;
    card.dataset.reeloEnhanced='1';

    const oldOverlay=[].slice.call(card.children).find(function(el){return (el.getAttribute('style')||'').indexOf('z-index:2')!==-1;});
    if(oldOverlay) oldOverlay.style.pointerEvents='none';

    const controls=document.createElement('div');
    controls.className='reelo-video-controls';
    controls.innerHTML='<button class="reelo-play" type="button" aria-label="Play video">▶</button>';
    card.appendChild(controls);

    const soundWrap=document.createElement('div');
    soundWrap.className='reelo-sound-wrap';
    soundWrap.innerHTML='<button class="reelo-sound" type="button" aria-label="Turn sound on">🔇</button>';
    card.appendChild(soundWrap);

    const progress=document.createElement('div');
    progress.className='reelo-progress';
    progress.setAttribute('role','slider');
    progress.setAttribute('aria-label','Video progress');
    progress.innerHTML='<span></span>';
    card.appendChild(progress);

    const play=controls.querySelector('.reelo-play');
    const sound=soundWrap.querySelector('.reelo-sound');
    const bar=progress.querySelector('span');

    function sync(){
      const playing=!video.paused&&!video.ended;
      play.textContent=playing?'Ⅱ':'▶';
      play.setAttribute('aria-label',playing?'Pause video':'Play video');
      sound.textContent=video.muted?'🔇':'🔊';
      sound.setAttribute('aria-label',video.muted?'Turn sound on':'Mute video');
      if(video.duration) bar.style.width=((video.currentTime/video.duration)*100)+'%';
    }

    play.addEventListener('click',function(e){
      e.stopPropagation();
      if(video.paused) video.play().catch(function(){}); else video.pause();
    });

    sound.addEventListener('click',function(e){
      e.stopPropagation();
      document.querySelectorAll('.video-card video').forEach(function(v){if(v!==video)v.muted=true;});
      video.muted=!video.muted;
      if(!video.muted) video.play().catch(function(){});
      sync();
    });

    progress.addEventListener('click',function(e){
      e.stopPropagation();
      if(!video.duration) return;
      const r=progress.getBoundingClientRect();
      const ratio=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
      video.currentTime=ratio*video.duration;
      sync();
    });

    video.addEventListener('timeupdate',sync);
    video.addEventListener('loadedmetadata',sync);
    video.addEventListener('play',sync);
    video.addEventListener('pause',sync);
    video.addEventListener('ended',sync);
    video.addEventListener('volumechange',sync);

    video.addEventListener('click',function(e){
      if(e.target.closest('.actions,.reelo-video-controls,.reelo-sound-wrap,.reelo-progress')) return;
      if(video.paused) video.play().catch(function(){}); else video.pause();
    });

    video.addEventListener('dblclick',function(e){
      e.preventDefault();
      e.stopPropagation();
      const like=card.querySelector('.actions .act');
      const liked=like && like.textContent.trim().indexOf('♥')===0;
      if(!liked && typeof window.likeVideo==='function') window.likeVideo(card.dataset.id,like);
      if(like){like.classList.remove('reelo-liked-pop');void like.offsetWidth;like.classList.add('reelo-liked-pop');}
      const heart=document.createElement('div');
      heart.className='reelo-heart-burst';
      heart.textContent='♥';
      card.appendChild(heart);
      setTimeout(function(){heart.remove();},800);
    });

    sync();
  }

  function injectStyle(){
    if(document.getElementById('reelo-interactions-style')) return;
    const style=document.createElement('style');
    style.id='reelo-interactions-style';
    style.textContent=''
      +'.reelo-video-controls{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:20;pointer-events:none} '
      +'.reelo-play{width:56px;height:56px;border:1px solid rgba(255,255,255,.24);border-radius:50%;background:rgba(0,0,0,.42);backdrop-filter:blur(12px);color:#fff;font-size:21px;display:grid;place-items:center;cursor:pointer;pointer-events:auto;box-shadow:0 8px 28px rgba(0,0,0,.3)} '
      +'.reelo-play:active,.reelo-sound:active{transform:scale(.9)} '
      +'.reelo-sound-wrap{position:absolute;right:18px;bottom:92px;z-index:20} '
      +'.reelo-sound{width:42px;height:42px;border:1px solid rgba(255,255,255,.22);border-radius:50%;background:rgba(0,0,0,.38);backdrop-filter:blur(10px);color:#fff;font-size:17px;cursor:pointer} '
      +'.reelo-progress{position:absolute;left:16px;right:16px;bottom:76px;height:4px;border-radius:99px;background:rgba(255,255,255,.24);z-index:21;cursor:pointer;overflow:hidden} '
      +'.reelo-progress span{display:block;height:100%;width:0;border-radius:inherit;background:#fff;box-shadow:0 0 8px rgba(255,255,255,.5)} '
      +'.video-card:before,.video-card:after{display:none!important} '
      +'.reelo-heart-burst{position:absolute;left:50%;top:48%;transform:translate(-50%,-50%) scale(.4);font-size:92px;line-height:1;color:#fff;filter:drop-shadow(0 8px 22px rgba(0,0,0,.45));z-index:30;pointer-events:none;animation:reeloHeart .75s cubic-bezier(.2,.8,.2,1) forwards} '
      +'@keyframes reeloHeart{0%{opacity:0;transform:translate(-50%,-50%) scale(.35)}25%{opacity:1;transform:translate(-50%,-50%) scale(1.15)}65%{opacity:1;transform:translate(-50%,-50%) scale(1)}100%{opacity:0;transform:translate(-50%,-58%) scale(.85)}} '
      +'.reelo-liked-pop{animation:reeloLikePop .38s ease} '
      +'@keyframes reeloLikePop{50%{transform:scale(1.18)}100%{transform:scale(1)}}';
    document.head.appendChild(style);
  }

  function scan(){document.querySelectorAll('.video-card').forEach(enhanceCard);}
  function init(){
    injectStyle();
    scan();
    new MutationObserver(scan).observe(document.body,{childList:true,subtree:true});
    document.addEventListener('keydown',function(e){
      if(e.target.matches('input,textarea')) return;
      const card=document.querySelector('.video-card video');
      if(!card) return;
      if(e.code==='Space'){e.preventDefault();if(card.paused)card.play().catch(function(){});else card.pause();}
      if(e.key.toLowerCase()==='m'){card.muted=!card.muted;if(!card.muted)card.play().catch(function(){});}
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();