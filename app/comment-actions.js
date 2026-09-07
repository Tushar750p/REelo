(function(){
  const style=document.createElement('style');
  style.textContent='.comment-actions{position:absolute;inset:0;background:#0009;z-index:95;display:none;align-items:flex-end}.comment-actions.show{display:flex}.comment-actions-card{width:100%;background:#111;border:1px solid #2b2b2b;border-radius:22px 22px 0 0;padding:14px 16px calc(18px + env(safe-area-inset-bottom));box-shadow:0 -12px 40px #0008}.comment-action{width:100%;border:1px solid #2b2b2b;background:#181818;color:#fff;border-radius:13px;padding:14px;text-align:left;margin-top:8px;font-weight:700}.comment-action.danger{color:#ffb4b4}.comment-action.cancel{text-align:center;color:#aaa}';
  document.head.appendChild(style);
  let state={id:null,userId:null,username:null};
  function escLocal(s){return String(s??'').replace(/[&<>\\\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\\\"':'&quot;',"'":'&#39;'}[c]))}
  function ensureSheet(){
    if(document.getElementById('commentActions'))return document.getElementById('commentActions');
    const el=document.createElement('section');
    el.id='commentActions';el.className='comment-actions';
    el.innerHTML='<div class="comment-actions-card"><div class="report-head"><b>Comment options</b><button class="back" type="button" aria-label="Close">×</button></div><div id="commentActionButtons"></div></div>';
    el.addEventListener('click',e=>{if(e.target===el)closeActions()});
    el.querySelector('.back').addEventListener('click',closeActions);
    document.querySelector('.shell')?.appendChild(el);
    return el;
  }
  function closeActions(){state={id:null,userId:null,username:null};document.getElementById('commentActions')?.classList.remove('show')}
  async function openActions(id){
    if(typeof token==='undefined'||!token){openAuth('login');return}
    state.id=id;
    const sheet=ensureSheet();
    const box=document.getElementById('commentActionButtons');
    box.innerHTML='<button class="comment-action" disabled>Loading options…</button>';
    sheet.classList.add('show');
    try{
      const r=await fetch(API+`/api/videos/${encodeURIComponent(commentVideoId)}/comments?limit=100&offset=0`,{headers:headers()});
      if(!r.ok)throw Error();
      const d=await r.json();
      const c=d.items.find(x=>String(x.id)===String(id));
      if(!c)throw Error('Comment not found');
      state.userId=c.user_id;state.username=c.username||'user';
      const own=me&&String(me.id)===String(c.user_id);
      box.innerHTML=(own?'<button class="comment-action danger" type="button" data-action="delete">Delete comment</button>':`<button class="comment-action" type="button" data-action="block">Block @${escLocal(c.username||'user')}</button>`)+ '<button class="comment-action" type="button" data-action="report">Report comment</button><button class="comment-action cancel" type="button" data-action="cancel">Cancel</button>';
      box.onclick=e=>{const b=e.target.closest('[data-action]');if(!b)return;const a=b.dataset.action;if(a==='delete')deleteComment();else if(a==='block')blockUser();else if(a==='report')reportComment();else closeActions()};
    }catch(e){box.innerHTML='<button class="comment-action" type="button" data-action="cancel">Comment unavailable · Close</button>'}
  }
  async function deleteComment(){
    const id=state.id;if(!id)return;
    try{const r=await fetch(API+`/api/community/comments/${encodeURIComponent(id)}`,{method:'DELETE',headers:headers()});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'Could not delete comment');closeActions();await loadComments(true);toast('Comment deleted')}catch(e){toast(e.message||'Could not delete comment')}
  }
  async function blockUser(){
    const uid=state.userId,name=state.username;if(!uid)return;
    try{const r=await fetch(API+`/api/community/users/${encodeURIComponent(uid)}/block`,{method:'POST',headers:headers()});const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'Could not block user');closeActions();closeComments();await loadFeed();toast('@'+name+' blocked')}catch(e){toast(e.message||'Could not block user')}
  }
  function reportComment(){const id=state.id;closeActions();if(id)openCommentReport(id)}
  document.addEventListener('click',function(e){
    const btn=e.target.closest('.comment-menu');
    if(!btn)return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
    const m=(btn.getAttribute('onclick')||'').match(/openCommentReport\\(['\"]([^'\"]+)['\"]\\)/);
    if(m)openActions(m[1]);
  },true);
})();
