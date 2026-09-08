(function(){
  const VIDEO_SELECTOR='.video-card video';
  const API=window.REELO_API||location.origin;
  const cache=new Map();
  const pending=new Map();

  function networkProfile(){
    const c=navigator.connection||navigator.mozConnection||navigator.webkitConnection;
    if(!c)return '540p';
    if(c.saveData)return '360p';
    const type=String(c.effectiveType||'').toLowerCase();
    if(type==='slow-2g'||type==='2g'||type==='3g')return '360p';
    return '720p';
  }

  function absolute(url){
    if(!url)return '';
    try{return new URL(url,API).href;}catch(_){return url;}
  }

  function nativeHls(video){
    return !!(video.canPlayType&&video.canPlayType('application/vnd.apple.mpegurl'));
  }

  function sourceKey(video){
    const src=video.currentSrc||video.getAttribute('src')||'';
    return src;
  }

  async function metadata(video){
    const key=sourceKey(video);
    if(!key||!key.includes('/media/'))return null;
    if(cache.has(key))return cache.get(key);
    if(pending.has(key))return pending.get(key);
    let filename='';
    try{filename=decodeURIComponent(new URL(key,location.href).pathname.split('/').pop()||'');}catch(_){return null;}
    if(!filename)return null;
    const promise=fetch(API+'/api/videos/playback?filename='+encodeURIComponent(filename),{credentials:'same-origin'})
      .then(r=>r.ok?r.json():null)
      .then(data=>{if(data)cache.set(key,data);return data;})
      .catch(()=>null)
      .finally(()=>pending.delete(key));
    pending.set(key,promise);
    return promise;
  }

  function pickVariant(data){
    if(!data||!Array.isArray(data.variants)||!data.variants.length)return null;
    const wanted=networkProfile();
    const order={"360p":0,"540p":1,"720p":2};
    const sorted=data.variants.slice().sort((a,b)=>(order[a.profile]??99)-(order[b.profile]??99));
    const exact=sorted.find(v=>v.profile===wanted);
    if(exact)return exact;
    return sorted.reduce((best,v)=>{
      if(!best)return v;
      return Math.abs((order[v.profile]??99)-(order[wanted]??1))<Math.abs((order[best.profile]??99)-(order[wanted]??1))?v:best;
    },null);
  }

  async function prepare(video){
    if(video.dataset.reeloAdaptive==='1'||video.dataset.reeloAdaptiveLoading==='1')return;
    video.dataset.reeloAdaptiveLoading='1';
    const original=video.currentSrc||video.getAttribute('src')||'';
    const data=await metadata(video);
    video.dataset.reeloAdaptiveLoading='0';
    if(!data)return;

    if(data.thumbnail&&!video.poster)video.poster=absolute(data.thumbnail);

    if(data.hls_url&&nativeHls(video)){
      if(video.src!==absolute(data.hls_url)){
        const wasPlaying=!video.paused;
        const time=video.currentTime||0;
        video.src=absolute(data.hls_url);
        video.load();
        if(wasPlaying){
          const p=video.play();
          if(p&&p.catch)p.catch(()=>{});
        }
        if(Number.isFinite(time)&&time>0)video.addEventListener('loadedmetadata',()=>{try{video.currentTime=time;}catch(_){ }},{once:true});
      }
      video.dataset.reeloAdaptive='1';
      video.dataset.reeloPlayback='hls';
      return;
    }

    const variant=pickVariant(data);
    if(variant){
      const url=absolute(variant.url);
      if(url&&url!==absolute(original)){
        const wasPlaying=!video.paused;
        const muted=video.muted;
        video.src=url;
        video.muted=muted;
        video.load();
        if(wasPlaying){const p=video.play();if(p&&p.catch)p.catch(()=>{});}
      }
      video.dataset.reeloPlayback=variant.profile||'mp4';
    }
    video.dataset.reeloAdaptive='1';
  }

  function scan(root){
    (root||document).querySelectorAll(VIDEO_SELECTOR).forEach(video=>prepare(video));
  }

  scan(document);
  const feed=document.getElementById('feed')||document.querySelector('.feed')||document.body;
  new MutationObserver(()=>scan(feed)).observe(feed,{childList:true,subtree:true});
  feed.addEventListener('scroll',()=>{
    const active=feed.querySelector('.video-card video');
    if(active)prepare(active);
  },{passive:true});
  window.addEventListener('online',()=>scan(feed));
  window.addEventListener('connectionchange',()=>scan(feed));
})();
