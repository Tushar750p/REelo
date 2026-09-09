(function(){
  'use strict';
  const params=new URLSearchParams(location.search);
  const videoId=params.get('video');
  if(!videoId)return;
  let handled=false;
  function findCard(){
    const id=String(videoId);
    return Array.from(document.querySelectorAll('[data-id]')).find(el=>String(el.getAttribute('data-id'))===id)||null;
  }
  function openSharedVideo(){
    if(handled)return true;
    const card=findCard();
    if(!card)return false;
    handled=true;
    card.scrollIntoView({behavior:'instant',block:'center'});
    card.classList.add('reelo-shared-target');
    setTimeout(()=>card.classList.remove('reelo-shared-target'),1800);
    const media=card.querySelector('video');
    if(media){try{media.muted=true;const p=media.play();if(p&&p.catch)p.catch(()=>{});}catch(e){}}
    return true;
  }
  const style=document.createElement('style');
  style.textContent='.reelo-shared-target{outline:2px solid rgba(255,255,255,.9);outline-offset:-2px;box-shadow:0 0 0 9999px rgba(0,0,0,.06),0 0 28px rgba(255,255,255,.28);transition:box-shadow .2s ease}';
  document.head.appendChild(style);
  const timer=setInterval(()=>{if(openSharedVideo())clearInterval(timer)},300);
  setTimeout(()=>clearInterval(timer),15000);
  window.addEventListener('load',openSharedVideo,{once:true});
})();
