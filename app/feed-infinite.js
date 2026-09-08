(function(){
  let loading=false,offset=0,done=false,lastMode='';
  const PAGE=12;
  function api(){return window.REELO_API||'http://localhost:8000';}
  function auth(){const t=localStorage.getItem('reelo_token')||'';return t?{'Authorization':'Bearer '+t}:{};}
  function mode(){return typeof currentTab!=='undefined'&&currentTab==='Following'?'following':'for_you';}
  function reset(){offset=0;done=false;lastMode=mode();}
  async function loadMore(){
    if(loading||done||mode()!=='for_you')return;
    const t=localStorage.getItem('reelo_token')||'';if(!t)return;
    loading=true;
    try{
      const r=await fetch(api()+'/api/recommendations?limit='+PAGE+'&offset='+offset,{headers:auth()});
      if(!r.ok)throw Error();
      const d=await r.json();
      const items=Array.isArray(d.items)?d.items:[];
      const existing=new Set((typeof feedItems!=='undefined'?feedItems:[]).map(v=>String(v.id)));
      const fresh=items.filter(v=>v&&v.id!=null&&!existing.has(String(v.id)));
      if(fresh.length){
        if(typeof feedItems!=='undefined')feedItems.push(...fresh);
        if(typeof render==='function')render();
      }
      offset+=items.length;
      done=!d.has_more||items.length===0;
    }catch(e){}finally{loading=false;}
  }
  function nearBottom(){
    if(mode()!==lastMode){reset();return;}
    if(window.innerHeight+window.scrollY>=document.documentElement.scrollHeight-1200)loadMore();
  }
  window.addEventListener('scroll',nearBottom,{passive:true});
  window.addEventListener('resize',nearBottom,{passive:true});
  document.addEventListener('click',()=>{setTimeout(()=>{if(mode()!==lastMode)reset();nearBottom()},250),true});
  setInterval(()=>{if(mode()!==lastMode)reset();},800);
})();
