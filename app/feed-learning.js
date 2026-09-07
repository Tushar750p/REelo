(function(){
  const active=new Map();
  const sent=new Map();
  const API='/api/recommendations/feedback';

  function token(){return localStorage.getItem('reelo_token')||localStorage.getItem('token')||'';}
  function cardId(card){return card&&card.dataset.id?String(card.dataset.id):'';}
  function send(videoId,action,seconds){
    if(!videoId||!token())return;
    const key=videoId+'|'+action;
    if(action==='impression'&&sent.has(key))return;
    sent.set(key,1);
    const body=JSON.stringify({video_id:videoId,action,seconds:Number((seconds||0).toFixed(2))});
    const headers={'Content-Type':'application/json','Authorization':'Bearer '+token()};
    try{fetch(API,{method:'POST',headers,body,keepalive:true}).catch(()=>{});}catch(e){}
  }
  function start(card){
    const id=cardId(card);if(!id||active.has(card))return;
    const state={id,started:performance.now(),last:performance.now(),seconds:0,watchSent:0};
    active.set(card,state);send(id,'impression',0);
  }
  function stop(card,ratio){
    const s=active.get(card);if(!s)return;
    s.seconds+=Math.max(0,(performance.now()-s.last)/1000);active.delete(card);
    if(s.seconds>=1)send(s.id,'watch',s.seconds);
    if(ratio<0.2&&s.seconds<3)send(s.id,'skip',s.seconds);
  }
  function tick(){
    active.forEach((s,card)=>{
      const now=performance.now();s.seconds+=Math.max(0,(now-s.last)/1000);s.last=now;
      if(s.seconds-s.watchSent>=8){s.watchSent=s.seconds;send(s.id,'progress',s.seconds);}
      const v=card.querySelector('video');
      if(v&&Number.isFinite(v.duration)&&v.duration>0&&v.currentTime/v.duration>=0.92&&!s.complete){s.complete=true;send(s.id,'complete',s.seconds);}
    });
  }
  const observer=new IntersectionObserver(entries=>entries.forEach(e=>{
    if(e.isIntersecting&&e.intersectionRatio>=0.68)start(e.target);
    else if(!e.isIntersecting||e.intersectionRatio<0.2)stop(e.target,e.intersectionRatio);
  }),{threshold:[0.2,0.68,0.92]});
  function scan(){document.querySelectorAll('.video-card').forEach(c=>{if(c.dataset.reeloLearning!=='1'){c.dataset.reeloLearning='1';observer.observe(c);}});}
  scan();setInterval(tick,2000);
  const root=document.getElementById('feed')||document.body;
  new MutationObserver(scan).observe(root,{childList:true,subtree:true});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)active.forEach((_,card)=>stop(card,0));});
  window.addEventListener('pagehide',()=>active.forEach((_,card)=>stop(card,0)));

  document.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    const card=b.closest('.video-card');if(!card)return;const id=cardId(card);if(!id)return;
    const label=(b.getAttribute('aria-label')||b.textContent||'').toLowerCase();
    if(label.includes('like'))send(id,'like',active.get(card)?.seconds||0);
    else if(label.includes('comment'))send(id,'comment',active.get(card)?.seconds||0);
    else if(label.includes('share'))send(id,'share',active.get(card)?.seconds||0);
    else if(label.includes('save'))send(id,'save',active.get(card)?.seconds||0);
  },true);
})();
