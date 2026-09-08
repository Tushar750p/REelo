(function(){
  const API=window.REELO_API||'http://localhost:8000';
  function addEditorButton(){
    const sheet=document.getElementById('uploadSheet'); if(!sheet||sheet.dataset.enhanced)return;
    sheet.dataset.enhanced='1';
    const post=sheet.querySelector('.primary');
    if(!post)return;
    const b=document.createElement('button');
    b.className='secondary'; b.type='button'; b.style.marginTop='9px'; b.textContent='🎬 Edit video';
    b.onclick=()=>{const f=document.getElementById('videoFile')?.files?.[0];if(!f){alert('Choose a video first.');return} openEditor(f)};
    post.parentNode.insertBefore(b,post);
    const s=document.createElement('button');
    s.className='secondary'; s.type='button'; s.style.marginTop='9px'; s.textContent='🎵 Choose sound';
    s.onclick=()=>location.href='sounds.html';
    post.parentNode.insertBefore(s,post);
    const file=document.getElementById('videoFile');
    file?.addEventListener('change',()=>{const f=file.files?.[0];if(f){let n=sheet.querySelector('.editor-note');if(!n){n=document.createElement('div');n.className='editor-note';n.style='color:#999;font-size:12px;margin-top:7px';sheet.appendChild(n)}n.textContent=`${(f.size/1024/1024).toFixed(1)} MB ready — Edit video for trim, speed, filters & sound.`}});
  }
  function openEditor(file){
    const url=URL.createObjectURL(file);
    const old=document.getElementById('reeloEditorOverlay');old?.remove();
    const el=document.createElement('section');el.id='reeloEditorOverlay';el.style='position:absolute;inset:0;background:#050505;z-index:110;overflow:auto';
    el.innerHTML=`<div style="position:sticky;top:0;z-index:3;height:58px;display:flex;align-items:center;justify-content:space-between;padding:0 15px;background:#0b0b0bf5;border-bottom:1px solid #292929"><button id="editorClose" style="border:0;background:none;color:#fff;font-size:15px">‹ Back</button><b>REelo Editor</b><button id="editorPublish" style="border:0;background:#fff;color:#000;border-radius:10px;padding:9px 13px;font-weight:800">Publish</button></div><div style="height:48vh;display:grid;place-items:center;background:#000"><video id="editorPreview" controls playsinline style="max-width:100%;max-height:100%" src="${url}"></video></div><div style="padding:15px"><label>Trim start</label><input id="edStart" type="number" min="0" step="0.1" placeholder="0" style="width:100%;margin:7px 0 12px;padding:12px;background:#171717;border:1px solid #333;border-radius:10px;color:#fff"><label>Trim end</label><input id="edEnd" type="number" min="0" step="0.1" placeholder="Full video" style="width:100%;margin:7px 0 12px;padding:12px;background:#171717;border:1px solid #333;border-radius:10px;color:#fff"><label>Speed</label><select id="edSpeed" style="width:100%;margin:7px 0 12px;padding:12px;background:#171717;border:1px solid #333;border-radius:10px;color:#fff"><option value="1">1× Normal</option><option value="0.5">0.5×</option><option value="1.5">1.5×</option><option value="2">2×</option></select><label>Filter</label><select id="edFilter" style="width:100%;margin:7px 0 12px;padding:12px;background:#171717;border:1px solid #333;border-radius:10px;color:#fff"><option>none</option><option>mono</option><option>warm</option><option>cool</option></select><input id="edCaption" placeholder="Write a caption…" style="width:100%;padding:12px;background:#171717;border:1px solid #333;border-radius:10px;color:#fff"></div>`;
    document.querySelector('.shell')?.appendChild(el);
    const p=el.querySelector('#editorPreview');
    el.querySelector('#editorClose').onclick=()=>{URL.revokeObjectURL(url);el.remove()};
    el.querySelector('#edSpeed').onchange=e=>p.playbackRate=Number(e.target.value);
    el.querySelector('#edFilter').onchange=e=>p.style.filter={none:'none',mono:'grayscale(1)',warm:'sepia(.35) saturate(1.2)',cool:'saturate(.85) hue-rotate(12deg)'}[e.target.value];
    el.querySelector('#editorPublish').onclick=async()=>{
      const t=localStorage.getItem('reelo_token')||'';if(!t){alert('Please login first.');return}
      const b=el.querySelector('#editorPublish');b.disabled=true;b.textContent='Processing…';
      const fd=new FormData();fd.append('file',file);fd.append('caption',el.querySelector('#edCaption').value);fd.append('start',el.querySelector('#edStart').value);fd.append('end',el.querySelector('#edEnd').value);fd.append('speed',el.querySelector('#edSpeed').value);fd.append('filter_name',el.querySelector('#edFilter').value);fd.append('rotate','0');fd.append('flip','false');fd.append('mute','false');
      const selected=new URLSearchParams(location.search).get('useSound')||localStorage.getItem('reelo_selected_sound')||'';if(selected)fd.append('sound_id',selected);
      try{const r=await fetch(API+'/api/editor/publish',{method:'POST',headers:{Authorization:'Bearer '+t},body:fd});const d=await r.json();if(!r.ok)throw Error(d.detail||'Publish failed');localStorage.removeItem('reelo_selected_sound');alert('Video published successfully!');location.reload()}catch(e){alert(e.message||'Publish failed');b.disabled=false;b.textContent='Publish'}
    };
  }
  window.addEventListener('load',addEditorButton);
  new MutationObserver(addEditorButton).observe(document.documentElement,{childList:true,subtree:true});
})();