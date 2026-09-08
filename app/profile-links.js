(function(){
  function usernameFromCard(card){
    if(!card)return '';
    const explicit=card.getAttribute('data-username')||card.dataset?.username||card.querySelector('[data-username]')?.getAttribute('data-username');
    if(explicit)return String(explicit).replace(/^@/,'').trim();
    const handle=card.querySelector('.handle');
    if(handle){
      const text=(handle.textContent||'').trim();
      const match=text.match(/@([a-zA-Z0-9._-]{1,30})/);
      if(match)return match[1];
      if(/^[a-zA-Z0-9._-]{1,30}$/.test(text))return text;
    }
    return '';
  }
  document.addEventListener('click',function(e){
    const target=e.target.closest('.video-card .creator .avatar,.video-card .creator .handle,.video-card .creator');
    if(!target)return;
    const card=target.closest('.video-card');
    const username=usernameFromCard(card);
    if(!username)return;
    if(e.target.closest('.follow'))return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
    location.href='profile.html?username='+encodeURIComponent(username);
  },true);
  function scan(){
    document.querySelectorAll('.video-card .creator').forEach(el=>{
      if(el.dataset.profileLinkReady)return;
      el.dataset.profileLinkReady='1';
      el.style.cursor='pointer';
      el.setAttribute('role','link');
      el.setAttribute('tabindex','0');
    });
  }
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter'&&e.key!==' ')return;
    const el=e.target.closest('.video-card .creator');
    if(!el)return;
    e.preventDefault();el.click();
  });
  new MutationObserver(scan).observe(document.getElementById('feed')||document.body,{childList:true,subtree:true});
  window.addEventListener('load',scan);setInterval(scan,1500);
})();
