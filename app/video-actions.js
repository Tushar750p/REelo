(function(){
  const style=document.createElement('style');
  style.textContent='.video-actions{position:absolute;inset:0;background:#0009;z-index:96;display:none;align-items:flex-end}.video-actions.show{display:flex}.video-actions-card{width:100%;background:#111;border:1px solid #2b2b2b;border-radius:22px 22px 0 0;padding:14px 16px calc(18px + env(safe-area-inset-bottom));box-shadow:0 -12px 40px #0008}.video-action{width:100%;border:1px solid #2b2b2b;background:#181818;color:#fff;border-radius:13px;padding:14px;text-align:left;margin-top:8px;font-weight:700}.video-action.danger{color:#ffb4b4}.video-action.cancel{text-align:center;color:#aaa}';
  document.head.appendChild(style);
  const NOT_INTERESTED='reelo_not_interested_videos';
  const MUTED_CREATORS='reelo_muted_creators';
  let state={id:null,userId:null,username:null};
  const readSet=k=>new Set(JSON.parse(localStorage.getItem(k)||'[]').map(String));
  const writeSet=(k,s)=>localStorage.setItem(k,JSON.stringify([...s]));
  function ensureSheet(){
    if(document.getElementById('videoActions'))return document.getElementById('videoActions');
    const el=document.createElement('section');
    el.id='videoActions';el.className='video-actions';
    el.innerHTML='<div class="video-actions-card"><div class="report-head"><b>Video options</b><button class="back" type="button" aria-label="Close">×</button></div><div id="videoActionButtons"></div></div>';
    el.addEventListener('click',e=>{if(e.target===el)closeActions()});
    el.querySelector('.back').addEventListener('click',closeActions);
    document.querySelector('.shell')?.appendChild(el);
    return el;
  }
  function closeActions(){state={id:null,userId:null,username:null};document.getElementById('videoActions')?.classList.remove('show')}
  function findVideo(id){return typeof feedItems!=='undefined'&&Array.isArray(feedItems)?feedItems.find(v=>String(v.id)===String(id)):null}
  function openActions(id){
    if(typeof token==='undefined'||!token){openAuth('login');return}
    const v=findVideo(id);
    state={id:String(id),userId:v?.user_id||null,username:v?.username||v?.display_name||'creator'};
    const sheet=ensureSheet(),box=document.getElementById('videoActionButtons');
    const creator=state.userId?String(state.userId):'';
    const muted=creator&&readSet(MUTED_CREATORS).has(creator);
    box.innerHTML='<button class="video-action" type="button" data-action="interest">'+(readSet(NOT_INTERESTED).has(state.id)?'Already marked not interested':'Not interested')+'</button>'+(creator?'<button class="video-action" type="button" data-action="mute">'+(muted?'Unmute @'+state.username:'Mute @'+state.username)+'</button><button class="video-action danger" type="button" data-action="block">Block @'+state.username+'</button>':'')+'<button class="video-action" type="button" data-action="report">Report video</button><button class="video-action" type="button" data-action="copy">Copy link</button><button class="video-action cancel" type="button" data-action="cancel">Cancel</button>';
    box.onclick=e=>{const b=e.target.closest('[data-action]');if(!b)return;const a=b.dataset.action;if(a==='interest')notInterested();else if(a==='mute')toggleMute();else if(a==='block')blockCreator();else if(a==='report')reportVideo();else if(a==='copy')copyLink();else closeActions()};
    sheet.classList.add('show');
  }
  function notInterested(){
    const s=readSet(NOT_INTERESTED);s.add(state.id);writeSet(NOT_INTERESTED,s);const id=state.id;closeActions();
    const card=document.querySelector('[data-id="'+CSS.escape(id)+'"]');card?.remove();
    toast('We’ll show fewer videos like this');
  }
  function toggleMute(){
    const uid=state.userId;if(!uid)return;const s=readSet(MUTED_CREATORS);const muted=s.has(String(uid));muted?s.delete(String(uid)):s.add(String(uid));writeSet(MUTED_CREATORS,s);const name=state.username;closeActions();applyFilters();toast(muted?'@'+name+' unmuted':'@'+name+' muted');
  }
  async function blockCreator(){
    const uid=state.userId,name=state.username;if(!uid)return;
    try{const r=await fetch(API+`/api/community/users/${encodeURIComponent(uid)}/block`,{method:'POST',headers:headers()});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'Could not block creator');closeActions();await loadFeed();toast('@'+name+' blocked')}catch(e){toast(e.message||'Could not block creator')}
  }
  function reportVideo(){const id=state.id;closeActions();if(id)openReport(id)}
  async function copyLink(){const id=state.id;try{const url=location.origin+location.pathname+'?video='+encodeURIComponent(id);await navigator.clipboard.writeText(url);closeActions();toast('Video link copied')}catch(e){toast('Could not copy link')}}
  function applyFilters(){
    const muted=readSet(MUTED_CREATORS),hidden=readSet(NOT_INTERESTED);
    document.querySelectorAll('[data-id]').forEach(el=>{const id=el.getAttribute('data-id');const v=findVideo(id);if(v&&(hidden.has(String(id))||(v.user_id&&muted.has(String(v.user_id)))))el.remove()});
  }
  document.addEventListener('click',function(e){
    const btn=e.target.closest('.more');
    if(!btn)return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
    const m=(btn.getAttribute('onclick')||'').match(/openReport\\(['\"]([^'\"]+)['\"]\\)/);
    if(m)openActions(m[1]);
  },true);
  const timer=setInterval(applyFilters,1200);
  window.addEventListener('beforeunload',()=>clearInterval(timer));
})();
