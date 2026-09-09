(function(){
  const API=window.REELO_API||location.origin;
  const token=()=>localStorage.getItem('reelo_token')||'';
  const auth=()=>token()?{Authorization:'Bearer '+token()}:{};
  const grid=()=>document.getElementById('grid');
  const json=async(url,opts={})=>{const r=await fetch(API+url,{...opts,headers:{'Content-Type':'application/json',...auth(),...(opts.headers||{})}});if(!r.ok)throw new Error(await r.text().catch(()=>''));return r.json()};
  let videoMap=new Map();
  async function loadVideoMap(){
    if(!token())return;
    try{
      const d=await json('/api/saves?limit=100');
      videoMap=new Map((d.items||[]).map(v=>[String(v.filename||''),String(v.id)]));
      enhanceTiles();
    }catch(_){ }
  }
  function enhanceTiles(){
    const root=grid();if(!root)return;
    root.querySelectorAll('.tile').forEach(tile=>{
      if(tile.dataset.reeloEnhanced==='1')return;
      const video=tile.querySelector('video');if(!video)return;
      const src=(video.getAttribute('src')||'').split('?')[0];
      const id=videoMap.get(src)||videoMap.get(src.replace(/^.*\//,''));
      if(!id)return;
      tile.dataset.videoId=id;tile.dataset.reeloEnhanced='1';tile.title='Open video';
      tile.style.cursor='pointer';
      tile.addEventListener('click',e=>{
        if(e.target.closest('button,a'))return;
        location.href='/index.html?video='+encodeURIComponent(id);
      });
      video.setAttribute('tabindex','-1');
    });
  }
  function collectionIdFromButton(btn){
    const s=btn.getAttribute('onclick')||'';const m=s.match(/showCollection\(['"]([^'"]+)['"]\)/);return m?m[1]:null;}
  function addManageButtons(){
    document.querySelectorAll('[onclick*="showCollection"]').forEach(tab=>{
      if(tab.dataset.manageAdded==='1')return;
      const id=collectionIdFromButton(tab);if(!id)return;
      tab.dataset.manageAdded='1';
      const b=document.createElement('button');b.type='button';b.textContent='⋯';b.title='Manage collection';b.className='reelo-collection-menu';
      b.style.cssText='margin-left:6px;border:0;background:transparent;color:inherit;cursor:pointer;font-size:16px;padding:0 3px;';
      b.addEventListener('click',async e=>{
        e.stopPropagation();
        const action=prompt('Type rename or delete');
        if(!action)return;
        try{
          if(action.toLowerCase()==='delete'){
            if(!confirm('Delete this collection? Saved videos will remain saved.'))return;
            await json('/api/saves/collections/'+encodeURIComponent(id),{method:'DELETE'});
            location.reload();
          }else if(action.toLowerCase()==='rename'){
            const name=prompt('New collection name');if(!name)return;
            await json('/api/saves/collections/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({name})});
            location.reload();
          }
        }catch(err){alert('Could not update collection.');}
      });
      tab.appendChild(b);
    });
  }
  function style(){
    if(document.getElementById('reelo-saved-enhanced-style'))return;
    const s=document.createElement('style');s.id='reelo-saved-enhanced-style';s.textContent='.tile[data-video-id]{transition:transform .16s ease,opacity .16s ease}.tile[data-video-id]:hover{transform:translateY(-2px)}.reelo-collection-menu:hover{opacity:.7}';document.head.appendChild(s);
  }
  function run(){style();addManageButtons();enhanceTiles();}
  loadVideoMap();
  run();
  const obs=new MutationObserver(()=>run());
  obs.observe(document.body,{childList:true,subtree:true});
  window.addEventListener('load',()=>{loadVideoMap();run()});
})();
