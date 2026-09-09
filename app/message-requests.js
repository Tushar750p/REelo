(()=>{
 const API=window.REELO_API||location.origin, token=localStorage.getItem('reelo_token')||'';
 if(!token || !/messages\.html$/i.test(location.pathname)) return;
 const H={Authorization:'Bearer '+token,'Content-Type':'application/json'};
 const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
 const css=`
 .reelo-msg-tabs{display:flex;gap:4px;padding:0 16px;border-bottom:1px solid #242424;background:inherit}
 .reelo-msg-tab{position:relative;border:0;background:transparent;color:#888;padding:13px 16px;font:800 14px system-ui;cursor:pointer}
 .reelo-msg-tab.active{color:#fff}.reelo-msg-tab.active:after{content:"";position:absolute;left:14px;right:14px;bottom:-1px;height:2px;background:#fff;border-radius:2px}
 .reelo-msg-tab-badge{display:inline-grid;place-items:center;min-width:17px;height:17px;margin-left:6px;padding:0 4px;border-radius:10px;background:#fff;color:#000;font-size:10px;vertical-align:middle}
 .reelo-requests-view{display:none;height:100%;overflow:auto}.reelo-requests-view.active{display:block}
 .reelo-request{padding:16px;border-bottom:1px solid #202020}.reelo-request-top{display:flex;gap:12px;align-items:center}
 .reelo-request-avatar{width:44px;height:44px;border-radius:50%;display:grid;place-items:center;background:#292929;font-weight:900;flex:none}
 .reelo-request-name{font-weight:850}.reelo-request-handle{font-size:12px;color:#888}.reelo-request-body{margin:12px 0;color:#ddd;line-height:1.45;word-break:break-word}
 .reelo-request-actions{display:flex;gap:8px}.reelo-request-actions button{border:0;border-radius:18px;padding:9px 14px;font-weight:800;cursor:pointer}
 .rr-accept{background:#fff;color:#000}.rr-delete,.rr-block{background:#242424;color:#fff}.reelo-empty{padding:50px 20px;text-align:center;color:#888}
 `;
 const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
 function findHost(){return document.querySelector('.messages-list,.conversation-list,.chat-list,[data-conversations]')||document.querySelector('main')||document.body}
 function findHeader(){return document.querySelector('.messages-header,.chat-header,header')||document.querySelector('main')?.firstElementChild||document.body.firstElementChild}
 const host=findHost();
 const header=findHeader();
 const tabs=document.createElement('div');tabs.className='reelo-msg-tabs';tabs.innerHTML='<button class="reelo-msg-tab active" data-tab="inbox">Inbox</button><button class="reelo-msg-tab" data-tab="requests">Requests<span class="reelo-msg-tab-badge" hidden>0</span></button>';
 const view=document.createElement('section');view.className='reelo-requests-view';view.innerHTML='<div class="reelo-empty">Loading requests…</div>';
 const list=view;
 if(header&&header.parentNode) header.parentNode.insertBefore(tabs,header.nextSibling); else document.body.prepend(tabs);
 if(host&&host.parentNode) host.parentNode.insertBefore(view,host.nextSibling); else document.body.appendChild(view);
 const inboxHost=host;
 const inboxDisplay=getComputedStyle(inboxHost).display;
 const badge=tabs.querySelector('.reelo-msg-tab-badge');
 const avatar=s=>String(s||'?').replace(/^@/,'').slice(0,1).toUpperCase();
 function switchTab(name){tabs.querySelectorAll('.reelo-msg-tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));if(name==='requests'){inboxHost.style.display='none';view.classList.add('active');refresh()}else{view.classList.remove('active');inboxHost.style.display=inboxDisplay==='none'?'block':inboxDisplay}}
 async function refresh(){try{const r=await fetch(API+'/api/message-requests?kind=inbox&limit=50',{headers:H});const d=await r.json();if(!r.ok)throw Error(d.detail||'Failed');const n=Number(d.total)||0;badge.textContent=n>99?'99+':String(n);badge.hidden=!n;if(!d.items?.length){list.innerHTML='<div class="reelo-empty">No new message requests</div>';return}list.innerHTML=d.items.map(x=>`<article class="reelo-request" data-id="${esc(x.id)}"><div class="reelo-request-top"><div class="reelo-request-avatar">${avatar(x.username)}</div><div><div class="reelo-request-name">${esc(x.display_name||x.username)}</div><div class="reelo-request-handle">@${esc(x.username)}</div></div></div><div class="reelo-request-body">${esc(x.body)}</div><div class="reelo-request-actions"><button class="rr-accept" data-action="accept">Accept</button><button class="rr-delete" data-action="delete">Delete</button><button class="rr-block" data-action="block">Block</button></div></article>`).join('')}catch(e){list.innerHTML='<div class="reelo-empty">Could not load requests.</div>'}}
 async function action(id,kind,card){const url=API+'/api/message-requests/'+encodeURIComponent(id)+(kind==='delete'?'':('/'+kind));const r=await fetch(url,{method:kind==='delete'?'DELETE':'POST',headers:H});const d=await r.json();if(!r.ok){alert(d.detail||'Action failed');return}if(kind==='accept'&&d.conversation_id){location.href='/messages.html?conversation_id='+encodeURIComponent(d.conversation_id)}else{card.remove();refresh()}}
 tabs.onclick=e=>{const b=e.target.closest('.reelo-msg-tab');if(b)switchTab(b.dataset.tab)};
 list.onclick=e=>{const b=e.target.closest('button[data-action]');if(!b)return;const card=b.closest('.reelo-request');action(card.dataset.id,b.dataset.action,card)};
 refresh();setInterval(refresh,10000);
})();
