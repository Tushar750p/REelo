(function(){
  const root=document.getElementById('feed')||document.querySelector('.feed');
  if(!root)return;
  const API=window.REELO_API||location.origin;
  const token=()=>localStorage.getItem('reelo_token')||'';
  const headers=()=>token()?{Authorization:'Bearer '+token()}:{};
  const cards=()=>[...root.querySelectorAll('.video-card')];
  function saveButton(card){return [...card.querySelectorAll('.actions .act')].find(b=>/saveVideo\s*\(/.test(b.getAttribute('onclick')||''));}
  async function syncCard(card){
    const id=card?.dataset?.id,btn=saveButton(card);if(!id||!btn||!token())return;
    try{
      const r=await fetch(API+'/api/saves/video/'+encodeURIComponent(id),{headers:headers()});
      if(!r.ok)return;
      const d=await r.json(),saved=!!d.saved,label=btn.querySelector('small');
      if(label)label.textContent=saved?'Saved':'Save';
      btn.setAttribute('aria-label',saved?'Unsave video':'Save video');
      btn.title=saved?'Remove from saved':'Save video';
      btn.classList.toggle('is-saved',saved);
    }catch(_){/* keep existing feed state */}
  }
  function removeDuplicateEnhancers(){
    cards().forEach(card=>{
      card.querySelectorAll('.reelo-save-action').forEach(b=>b.remove());
      card.querySelectorAll('.reelo-share-action').forEach(b=>b.remove());
    });
  }
  async function sync(){
    if(!token())return;
    removeDuplicateEnhancers();
    for(const card of cards().slice(0,12))await syncCard(card);
  }
  let timer;
  function schedule(){clearTimeout(timer);timer=setTimeout(sync,300)}
  sync();
  new MutationObserver(schedule).observe(root,{childList:true,subtree:true});
  window.addEventListener('load',schedule);
  setInterval(sync,10000);
})();
