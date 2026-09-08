(() => {
  const API = window.REELO_API || location.origin;
  const token = localStorage.getItem('reelo_token') || '';
  const headers = () => token ? { Authorization: 'Bearer ' + token } : {};
  const $ = id => document.getElementById(id);
  let liveRoomId = '';

  const originalFetch = window.fetch;
  window.fetch = async function(input, init) {
    try {
      const url = typeof input === 'string' ? input : input?.url || '';
      const m = url.match(/\/api\/live\/([^/?]+)(?:[/?]|$)/);
      if (m && !/\/guests(?:\/|$)|\/moderation|\/pin/.test(url)) liveRoomId = decodeURIComponent(m[1]);
    } catch (_) {}
    return originalFetch.apply(this, arguments);
  };

  function host() { return !!$('endBtn') && $('endBtn').style.display !== 'none'; }

  function addControls() {
    if (!host() || !$('guestPanel')) return;
    if (!$('liveModPanel')) {
      const p = document.createElement('div');
      p.id = 'liveModPanel';
      p.style.cssText = 'margin-top:12px;padding-top:10px;border-top:1px solid #292929;display:none';
      p.innerHTML = '<b style="font-size:12px">Host moderation</b><div id="liveModTarget" style="font-size:11px;color:#aaa;margin:6px 0">Select a guest</div><div style="display:flex;gap:6px;flex-wrap:wrap"><button data-mod="mute">🔇 Mute</button><button data-mod="block">🚫 Block</button><button data-mod="kick">👢 Kick</button></div>';
      p.querySelectorAll('button').forEach(b => { b.style.cssText='border:0;border-radius:8px;padding:7px 9px;font-weight:800;background:#292929;color:#fff'; b.onclick=()=>moderate(b.dataset.mod); });
      $('guestPanel').appendChild(p);
    }
    if (!$('pinBtn') && $('endBtn')) {
      const b=document.createElement('button'); b.id='pinBtn'; b.className='close'; b.textContent='📌 Pin'; b.style.marginLeft='4px'; b.onclick=pinComment; $('endBtn').before(b);
    }
    decorateGuests();
  }

  function selectGuest(id) {
    const p=$('liveModPanel'); if(!p)return;
    p.style.display='block'; $('liveModTarget').dataset.user=id; $('liveModTarget').textContent='Selected: '+id;
  }

  async function moderate(action) {
    const target=$('liveModTarget')?.dataset?.user;
    if(!liveRoomId||!target)return alert('Select a guest first.');
    const r=await originalFetch(API+'/api/live/'+encodeURIComponent(liveRoomId)+'/moderation',{method:'POST',headers:{...headers(),'Content-Type':'application/json'},body:JSON.stringify({action,value:target})});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)return alert(d.detail||'Moderation failed');
    if(action==='kick') await originalFetch(API+'/api/live/'+encodeURIComponent(liveRoomId)+'/guests/remove/'+encodeURIComponent(target),{method:'POST',headers:headers()});
    alert(action==='mute'?'Guest muted.':action==='block'?'Guest blocked.':'Guest removed.');
  }

  async function pinComment() {
    if(!liveRoomId)return;
    const id=prompt('Enter LIVE message ID to pin:'); if(!id)return;
    const r=await originalFetch(API+'/api/live/'+encodeURIComponent(liveRoomId)+'/pin?message_id='+encodeURIComponent(id),{method:'POST',headers:headers()});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)return alert(d.detail||'Unable to pin comment');
    alert('Comment pinned.');
  }

  function decorateGuests() {
    if(!host()||!$('guestList'))return;
    $('guestList').querySelectorAll('.guest-row').forEach(row=>{
      if(row.querySelector('.mod-select'))return;
      const span=row.querySelector('span'); const id=(span?.textContent||'').trim().split(/\s+/)[0]; if(!id)return;
      const b=document.createElement('button'); b.className='mod-select'; b.textContent='Controls'; b.style.cssText='border:0;border-radius:8px;padding:6px 8px;font-weight:800;background:#fff;color:#000'; b.onclick=()=>selectGuest(id); row.appendChild(b);
    });
  }

  setInterval(addControls,1500);
  setTimeout(addControls,500);
})();
