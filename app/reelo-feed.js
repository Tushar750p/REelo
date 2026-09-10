/* REelo Feed Interactions v1 */
(function(){
  'use strict';
  function enhanceCard(card){
    if(!card || card.dataset.reeloEnhanced) return;
    const video=card.querySelector('video');
    if(!video) return;
    card.dataset.reeloEnhanced='1';

    const controls=document.createElement('div');
    controls.className='reelo-video-controls';
    controls.innerHTML='<button class="reelo-sound" type="button" aria-label="Turn sound on" title="Sound">🔇</button><div class="reelo-progress"><span></span></div><div class="reelo-play">▶</div>';
    card.appendChild(controls);

    const sound=controls.querySelector('.reelo-sound');
    const progress=controls.querySelector('.reelo-progress');
    const bar=progress.querySelector('span');
    const playIcon=controls.querySelector('.reelo-play');

    sound.addEventListener('click',function(e){
      e.stopPropagation();
      video.muted=!video.muted;
      sound.textContent=video.muted?'🔇':'🔊';
      sound.setAttribute('aria-label',video.muted?'Turn sound on':'Mute sound');
      if(!video.muted) video.volume=.8;
    });

    progress.addEventListener('click',function(e){
      e.stopPropagation();
      if(!video.duration) return;
      const r=progress.getBoundingClientRect();
      video.currentTime=((e.clientX-r.left)/r.width)*video.duration;
    });

    video.addEventListener('timeupdate',function(){
      bar.style.width=video.duration?((video.currentTime/video.duration)*100)+'%':'0%';
    });
    video.addEventListener('play',function(){
      card.classList.remove('reelo-paused');
      playIcon.textContent='▶';
    });
    video.addEventListener('pause',function(){
      card.classList.add('reelo-paused');
      playIcon.textContent='▶';
    });

    card.addEventListener('click',function(e){
      if(e.target.closest('button,a,input,textarea,.actions,.bottom,.header,.reelo-video-controls')) return;
      if(video.paused) video.play().catch(function(){}); else video.pause();
    });

    card.addEventListener('dblclick',function(e){
      if(e.target.closest('button,a,.actions,.bottom,.header,.reelo-video-controls')) return;
      card.classList.remove('reelo-like-pop');
      void card.offsetWidth;
      card.classList.add('reelo-like-pop');
    });
  }

  function scan(){ document.querySelectorAll('.video-card').forEach(enhanceCard); }
  const observer=new MutationObserver(scan);
  function init(){
    scan();
    observer.observe(document.body,{childList:true,subtree:true});
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init); else init();
})();
