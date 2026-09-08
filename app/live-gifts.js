(() => {
  const API = window.REELO_API || location.origin;
  const token = localStorage.getItem('reelo_token') || '';
  const headers = () => token ? {Authorization:'Bearer '+token} : {};
  const $ = id => document.getElementById(id);
  let timer;
  async function api(path, options={}) {
    const r = await fetch(API+path,{...options,headers:{...headers(),...(options.headers||{})}});
    const d=await r.json().catch(()=>({}));
    if(!r.ok) throw new Error(d.detail||'Request failed');
    return d;
  }
  function panel(){
    if($('liveGiftPanel')) return;
    const host=$('guestPanel')||$('liveChat')||$('chatPanel');
    if(!host) return;
    const p=document.createElement('div'); p.id='liveGiftPanel';
    p.style.cssText='margin-top:10px;padding:10px;border:1px solid #292929;border-radius:14px;background:#111;color:#fff';
    p.innerHTML='<div style="display:flex;justify-content:space-between;align-items:center"><b>🎁 Gifts</b><span id="liveCoinBalance" style="font-size:12px;color:#aaa">🪙 0</span></div><div id="liveGiftGrid" style="display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:8px"></div><div id="liveGiftFeed" style="margin-top:8px;font-size:12px;color:#bbb"></div>';
    host.parentNode.insertBefore(p,host.nextSibling);
    loadCatalog(); loadWallet();
  }
  async function loadCatalog(){
    const room=window.room; if(!room) return;
    try { const d=await api('/api/live/'+encodeURIComponent(room)+'/gifts'); const g=$('liveGiftGrid'); if(!g)return; g.innerHTML=d.items.map(x=>`<button data-gift="${x.id}" style="border:1px solid #333;border-radius:10px;background:#191919;color:#fff;padding:8px 3px;font-size:18px;cursor:pointer">${x.emoji}<small style="display:block;font-size:10px">${x.coins} 🪙</small></button>`).join(''); g.querySelectorAll('button').forEach(b=>b.onclick=()=>send(b.dataset.gift)); } catch(e){}
  }
  async function loadWallet(){ const room=window.room;if(!room)return;try{const d=await api('/api/live/'+encodeURIComponent(room)+'/wallet');if($('liveCoinBalance'))$('liveCoinBalance').textContent='🪙 '+d.balance}catch(e){} }
  async function send(gift_id){ const room=window.room;if(!room)return;try{const d=await api('/api/live/'+encodeURIComponent(room)+'/gifts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({gift_id,quantity:1})});if($('liveCoinBalance'))$('liveCoinBalance').textContent='🪙 '+d.balance;loadFeed()}catch(e){alert(e.message)} }
  async function loadFeed(){ const room=window.room;if(!room)return;try{const d=await api('/api/live/'+encodeURIComponent(room)+'/gift-feed');if($('liveGiftFeed'))$('liveGiftFeed').innerHTML=d.items.slice(0,5).map(x=>`${x.gift.emoji||'🎁'} <b>${x.sender_id}</b> sent ${x.gift.name||x.gift_id} · ${x.coins} 🪙`).join('<br>')}catch(e){} }
  function start(){panel();loadWallet();loadFeed();clearInterval(timer);timer=setInterval(()=>{panel();loadWallet();loadFeed()},5000)}
  window.addEventListener('load',()=>setTimeout(start,700));
  window.addEventListener('reelo-live-ready',start);
})();
