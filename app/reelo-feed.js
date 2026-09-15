/* REelo Feed Interactions v10 — stable / no DOM observer */
(function(){
  'use strict';

  const FALLBACK=[
    {id:'demo-1',username:'reelo_creator',caption:'Build your vibe. Share your story. 🚀',filename:'https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4',likes:12400,comments:321},
    {id:'demo-2',username:'futuredaily',caption:'Create something people remember.',filename:'https://www.w3schools.com/html/mov_bbb.mp4',likes:8700,comments:142}
  ];

  function esc(s){
    return String(s||'').replace(/[&<>"']/g,function(m){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m];
    });
  }

  function enhanceCard(card){
    if(!card || card.dataset.reeloEnhanced) return;
    const video=card.querySelector('video');
    if(!video) return;
    card.dataset.reeloEnhanced='1';

    const controls=document.createElement('div');
    controls.className='reelo-video-controls';
    controls.innerHTML='<button class="reelo-play" type="button">▶</button>';
    card.appendChild(controls);

    const soundWrap=document.createElement('div');
    soundWrap.className='reelo-sound-wrap';
    soundWrap.innerHTML='<button class="reelo-sound" type="button">🔇</button>';
    card.appendChild(soundWrap);

    const progress=document.createElement('div');
    progress.className='reelo-progress';
    progress.innerHTML='<span></span>';
    card.appendChild(progress);

    const play=controls.querySelector('button');
    const sound=soundWrap.querySelector('button');
    const bar=progress.querySelector('span');

    function sync(){
      play.textContent=(!video.paused && !video.ended)?'Ⅱ':'▶';
      sound.textContent=video.muted?'🔇':'🔊';
      if(video.duration) bar.style.width=(video.currentTime/video.duration*100)+'%';
    }

    play.onclick=function(e){
      e.stopPropagation();
      if(video.paused) video.play().catch(function(){}); else video.pause();
    };

    sound.onclick=function(e){
      e.stopPropagation();
      document.querySelectorAll('.video-card video').forEach(function(v){if(v!==video)v.muted=true;});
      video.muted=!video.muted;
      if(!video.muted) video.play().catch(function(){});
      sync();
    };

    progress.onclick=function(e){
      e.stopPropagation();
      if(!video.duration) return;
      const r=progress.getBoundingClientRect();
      video.currentTime=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width))*video.duration;
    };

    ['timeupdate','loadedmetadata','play','pause','ended','volumechange'].forEach(function(type){video.addEventListener(type,sync);});

    video.onclick=function(e){
      if(e.target.closest('.actions,.reelo-video-controls,.reelo-sound-wrap,.reelo-progress')) return;
      if(video.paused) video.play().catch(function(){}); else video.pause();
    };

    video.ondblclick=function(e){
      e.preventDefault();
      e.stopPropagation();
      const like=card.querySelector('.actions .act');
      if(like && typeof window.likeVideo==='function') window.likeVideo(card.dataset.id,like);
      const heart=document.createElement('div');
      heart.className='reelo-heart-burst';
      heart.textContent='♥';
      card.appendChild(heart);
      setTimeout(function(){heart.remove();},700);
    };

    sync();
  }

  function injectStories(){
    if(document.getElementById('reelo-home-stories')) return;
    const shell=document.querySelector('.shell');
    const feed=document.getElementById('feed');
    if(!shell || !feed) return;
    const x=document.createElement('section');
    x.id='reelo-home-stories';
    x.className='reelo-home-stories';
    x.innerHTML='<div class="reelo-stories-head"><b>Stories</b><a href="stories.html">See all</a></div><div class="reelo-stories-row">'+
      '<button class="reelo-story" onclick="location.href=\'stories.html\'"><span class="reelo-story-ring"><span class="reelo-story-avatar reelo-add">＋</span></span><small>Your story</small></button>'+
      '<button class="reelo-story" onclick="location.href=\'stories.html\'"><span class="reelo-story-ring"><span class="reelo-story-avatar">R</span></span><small>REelo</small></button>'+
      '<button class="reelo-story" onclick="location.href=\'stories.html\'"><span class="reelo-story-ring"><span class="reelo-story-avatar">F</span></span><small>Future</small></button>'+
      '<button class="reelo-story" onclick="location.href=\'stories.html\'"><span class="reelo-story-ring"><span class="reelo-story-avatar">C</span></span><small>Creator</small></button>'+
      '<button class="reelo-story" onclick="location.href=\'stories.html\'"><span class="reelo-story-ring"><span class="reelo-story-avatar">A</span></span><small>Artist</small></button>'+
      '</div>';
    shell.insertBefore(x,feed);
  }

  function injectSuggested(){
    if(document.getElementById('reelo-suggested')) return;
    const shell=document.querySelector('.shell');
    const feed=document.getElementById('feed');
    if(!shell || !feed) return;
    const x=document.createElement('section');
    x.id='reelo-suggested';
    x.className='reelo-suggested';
    const creators=[['S','stylehub','Style Hub'],['M','musicroom','Music Room'],['T','techdaily','Tech Daily'],['C','creatorlab','Creator Lab']];
    x.innerHTML='<div class="reelo-suggested-head"><b>Suggested for you</b><button onclick="location.href=\'search.html\'">See all</button></div><div class="reelo-suggested-row">'+
      creators.map(function(c){return '<button class="reelo-suggested-card" onclick="location.href=\'search.html\'"><span class="reelo-suggested-avatar">'+c[0]+'</span><b>@'+c[1]+'</b><small>'+c[2]+'</small><span class="reelo-suggested-follow">Follow</span></button>';}).join('')+
      '</div>';
    shell.insertBefore(x,feed);
  }

  function injectStyle(){
    if(document.getElementById('reelo-interactions-style')) return;
    const s=document.createElement('style');
    s.id='reelo-interactions-style';
    s.textContent='.reelo-home-stories{position:absolute;top:62px;left:0;right:0;z-index:6;padding:8px 14px 10px;background:linear-gradient(180deg,rgba(0,0,0,.94),rgba(0,0,0,.68),transparent)}.reelo-stories-head{display:flex;justify-content:space-between;padding:0 4px 7px;font-size:13px}.reelo-stories-head a{color:#ddd;text-decoration:none;font-weight:700;font-size:12px}.reelo-stories-row{display:flex;gap:12px;overflow:auto;scrollbar-width:none}.reelo-story{border:0;background:none;color:#fff;min-width:58px;padding:0;display:flex;flex-direction:column;align-items:center;gap:4px}.reelo-story small{font-size:10px;max-width:58px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.reelo-story-ring{width:48px;height:48px;border-radius:50%;padding:2px;background:linear-gradient(135deg,#fff,#777,#222);display:grid;place-items:center}.reelo-story-avatar{width:100%;height:100%;border-radius:50%;background:#171717;border:2px solid #000;display:grid;place-items:center;font-weight:900}.reelo-story .reelo-add{background:#fff;color:#000;font-size:25px}.reelo-suggested{position:absolute;top:154px;left:0;right:0;z-index:6;padding:8px 14px 12px;background:rgba(0,0,0,.94)}.reelo-suggested-head{display:flex;justify-content:space-between;align-items:center;padding:0 4px 8px}.reelo-suggested-head b{font-size:13px}.reelo-suggested-head button{border:0;background:none;color:#bbb;font-size:11px;font-weight:800}.reelo-suggested-row{display:flex;gap:8px;overflow:auto;scrollbar-width:none}.reelo-suggested-card{min-width:112px;height:92px;padding:8px;border:1px solid #ffffff1f;border-radius:14px;background:#121216;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px}.reelo-suggested-avatar{width:32px;height:32px;border-radius:50%;display:grid;place-items:center;background:#eee;color:#111;font-weight:900}.reelo-suggested-card b{font-size:10px}.reelo-suggested-card small{font-size:9px;color:#888}.reelo-suggested-follow{margin-top:3px;width:100%;padding:4px;border-radius:8px;background:#fff;color:#000;font-size:9px;font-weight:900}.reelo-video-controls{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:20}.reelo-play{width:56px;height:56px;border:1px solid #ffffff3d;border-radius:50%;background:#0000006b;color:#fff;font-size:21px}.reelo-sound-wrap{position:absolute;right:18px;bottom:92px;z-index:20}.reelo-sound{width:42px;height:42px;border:1px solid #ffffff38;border-radius:50%;background:#00000061;color:#fff;font-size:17px}.reelo-progress{position:absolute;left:16px;right:16px;bottom:76px;height:4px;border-radius:99px;background:#ffffff3d;z-index:21;cursor:pointer;overflow:hidden}.reelo-progress span{display:block;height:100%;width:0;background:#fff}.reelo-heart-burst{position:absolute;left:50%;top:48%;transform:translate(-50%,-50%) scale(.4);font-size:92px;line-height:1;color:#fff;z-index:30;pointer-events:none;animation:reeloHeart .7s ease forwards}@keyframes reeloHeart{0%{opacity:0;transform:translate(-50%,-50%) scale(.35)}25%{opacity:1;transform:translate(-50%,-50%) scale(1.1)}100%{opacity:0;transform:translate(-50%,-58%) scale(.85)}}';
    document.head.appendChild(s);
  }

  function fallbackFeed(){
    const feed=document.getElementById('feed');
    if(!feed || feed.querySelector('.video-card')) return;
    feed.innerHTML=FALLBACK.map(function(v){
      return '<article class="video-card" data-id="'+v.id+'" style="min-height:520px"><video src="'+v.filename+'" loop playsinline muted preload="metadata"></video><div class="gradient"></div><div class="info"><div class="creator"><div class="avatar">'+v.username.charAt(0).toUpperCase()+'</div><span class="handle">@'+v.username+'</span></div><div class="caption">'+esc(v.caption)+'</div><div class="sound">♫ Original sound · REelo</div></div><div class="actions"><button class="act" onclick="likeVideo(\''+v.id+'\',this)">♡<small>'+v.likes+'</small></button><button class="act" onclick="openComments(\''+v.id+'\')">💬<small>'+v.comments+'</small></button><button class="act" onclick="shareVideo(\''+v.id+'\')">↗<small>Share</small></button><button class="act" onclick="saveVideo(\''+v.id+'\',this)">🔖<small>Save</small></button><button class="act more" onclick="openReport(\''+v.id+'\')">⋯</button></div></article>';
    }).join('');
    feed.querySelectorAll('.video-card').forEach(enhanceCard);
  }

  function forceLogin(){
    const a=document.getElementById('auth');
    if(!a) return;
    a.classList.add('show');
    a.style.display='flex';
    const u=document.getElementById('authUser');
    if(u) setTimeout(function(){u.focus();},50);
  }

  function init(){
    injectStyle();
    injectStories();
    injectSuggested();
    fallbackFeed();
    const p=new URLSearchParams(location.search);
    if(p.get('auth')==='login') forceLogin();
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
