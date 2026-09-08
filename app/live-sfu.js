(() => {
  const SFU_API = window.REELO_API || 'http://localhost:8000';
  const token = localStorage.getItem('reelo_token') || '';
  const SDK_URL = 'https://cdn.jsdelivr.net/npm/livekit-client@2.22.3/dist/livekit-client.umd.min.js';
  let lkRoom = null;
  let sdkPromise = null;

  const loadSdk = () => {
    if (window.LivekitClient) return Promise.resolve(window.LivekitClient);
    if (sdkPromise) return sdkPromise;
    sdkPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = SDK_URL;
      s.async = true;
      s.onload = () => window.LivekitClient ? resolve(window.LivekitClient) : reject(new Error('Live video client failed to load'));
      s.onerror = () => reject(new Error('Live video client failed to load'));
      document.head.appendChild(s);
    });
    return sdkPromise;
  };

  async function getLiveKitToken(room, role) {
    const r = await fetch(SFU_API + '/api/livekit/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: JSON.stringify({ room, role })
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || 'Live service unavailable');
    return d;
  }

  function stage() { return document.getElementById('stage'); }
  function camera() { return document.getElementById('camera'); }
  function chat() { return document.getElementById('chat'); }

  function ensureTileCss() {
    if (document.getElementById('reelo-livekit-css')) return;
    const s = document.createElement('style');
    s.id = 'reelo-livekit-css';
    s.textContent = '.sfu-grid{position:absolute;inset:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:3px;z-index:1}.sfu-tile{position:relative;min-width:0;min-height:0;background:#111;overflow:hidden}.sfu-tile video{width:100%;height:100%;object-fit:cover}.sfu-name{position:absolute;left:8px;bottom:8px;background:#0009;border-radius:10px;padding:4px 7px;font-size:11px}.sfu-local{position:absolute;right:12px;top:72px;width:104px;height:148px;border-radius:12px;overflow:hidden;background:#111;z-index:4;box-shadow:0 4px 20px #0008}.sfu-local video{width:100%;height:100%;object-fit:cover}.sfu-grid + .overlay,.sfu-grid~.overlay{z-index:5}.sfu-grid~.livebar,.sfu-grid~.chat,.sfu-grid~.reacts,.sfu-grid~.composer{z-index:6}.sfu-grid:empty{display:none}';
    document.head.appendChild(s);
  }

  function ensureGrid() {
    ensureTileCss();
    let grid = document.getElementById('sfuGrid');
    if (!grid) {
      grid = document.createElement('div');
      grid.id = 'sfuGrid';
      grid.className = 'sfu-grid';
      stage().prepend(grid);
    }
    return grid;
  }

  function addRemoteTrack(track, participant) {
    if (track.kind !== 'video') return;
    const grid = ensureGrid();
    const id = 'sfu-' + String(participant.identity || Math.random()).replace(/[^a-zA-Z0-9_-]/g, '_');
    let tile = document.getElementById(id);
    if (!tile) {
      tile = document.createElement('div');
      tile.id = id;
      tile.className = 'sfu-tile';
      grid.appendChild(tile);
      const label = document.createElement('span');
      label.className = 'sfu-name';
      label.textContent = participant.name || participant.identity || 'Live guest';
      tile.appendChild(label);
    }
    const el = track.attach();
    el.autoplay = true;
    el.playsInline = true;
    el.muted = false;
    el.className = 'sfu-remote-video';
    tile.querySelectorAll('video').forEach(v => v.remove());
    tile.prepend(el);
    camera().style.display = 'none';
  }

  function removeParticipant(participant) {
    const id = 'sfu-' + String(participant.identity || '').replace(/[^a-zA-Z0-9_-]/g, '_');
    document.getElementById(id)?.remove();
    const grid = document.getElementById('sfuGrid');
    if (grid && !grid.children.length) {
      grid.remove();
      camera().style.display = 'block';
    }
  }

  function showLocalPreview() {
    const grid = ensureGrid();
    let box = document.getElementById('sfuLocal');
    if (!box) {
      box = document.createElement('div');
      box.id = 'sfuLocal';
      box.className = 'sfu-local';
      grid.parentElement.appendChild(box);
    }
    const pubs = Array.from(lkRoom.localParticipant.videoTrackPublications.values());
    const pub = pubs.find(p => p.track);
    if (pub?.track) {
      box.innerHTML = '';
      const el = pub.track.attach();
      el.autoplay = true;
      el.playsInline = true;
      el.muted = true;
      box.appendChild(el);
    }
  }

  async function connectSFU(roomId, role) {
    if (!token) throw new Error('Login required');
    const LK = await loadSdk();
    const d = await getLiveKitToken(roomId, role);
    lkRoom = new LK.Room({ adaptiveStream: true, dynacast: true });
    const E = LK.RoomEvent;
    lkRoom.on(E.TrackSubscribed, (track, publication, participant) => addRemoteTrack(track, participant));
    lkRoom.on(E.TrackUnsubscribed, (track, publication, participant) => {
      track.detach().forEach(el => el.remove());
      if (participant) removeParticipant(participant);
    });
    lkRoom.on(E.ParticipantDisconnected, participant => removeParticipant(participant));
    lkRoom.on(E.LocalTrackPublished, () => showLocalPreview());
    lkRoom.on(E.Disconnected, () => { lkRoom = null; });
    await lkRoom.prepareConnection(d.url, d.token);
    await lkRoom.connect(d.url, d.token);

    if (role === 'host' || role === 'guest') {
      await lkRoom.localParticipant.setCameraEnabled(true, { resolution: { width: 720, height: 1280 } });
      await lkRoom.localParticipant.setMicrophoneEnabled(true);
      showLocalPreview();
    }
    return d;
  }

  async function enterRoom(id, role) {
    if (!token) { location.href = 'index.html?login=1'; return; }
    document.getElementById('home').style.display = 'none';
    stage().classList.add('show');
    document.getElementById('endBtn').style.display = role === 'host' ? 'block' : 'none';
    try {
      if (role !== 'host') {
        const jr = await fetch(SFU_API + '/api/live/' + encodeURIComponent(id) + '/join', { method: 'POST', headers: { Authorization: 'Bearer ' + token } });
        const jd = await jr.json().catch(() => ({}));
        if (!jr.ok) throw new Error(jd.detail || 'Unable to join LIVE');
      }
      await connectSFU(id, role);
      await window.refresh?.();
    } catch (e) {
      alert(e.message || 'Unable to connect to LIVE');
      location.href = 'live.html';
    }
  }

  window.startLive = async function () {
    if (!token) { location.href = 'index.html?login=1'; return; }
    const title = document.getElementById('title').value.trim() || 'Live on REelo';
    try {
      const r = await fetch(SFU_API + '/api/live', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
        body: JSON.stringify({ title })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || 'Unable to start LIVE');
      await enterRoom(d.id, 'host');
    } catch (e) { alert(e.message || 'Unable to start LIVE'); }
  };

  window.join = async function (id) { await enterRoom(id, 'viewer'); };

  const oldLeave = window.leaveRoom;
  window.leaveRoom = function (sendLeave = true) {
    try { lkRoom?.disconnect(); } catch (_) {}
    lkRoom = null;
    if (sendLeave && window.room) {
      fetch(SFU_API + '/api/live/' + encodeURIComponent(window.room) + '/leave', {
        method: 'POST', headers: { Authorization: 'Bearer ' + token }, keepalive: true
      }).catch(() => {});
    }
    if (typeof oldLeave === 'function') return oldLeave(sendLeave);
    location.href = 'live.html';
  };

  window.addEventListener('pagehide', () => { try { lkRoom?.disconnect(); } catch (_) {} });
})();
