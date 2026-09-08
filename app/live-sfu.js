(() => {
  const SFU_API = window.REELO_API || 'http://localhost:8000';
  const token = localStorage.getItem('reelo_token') || '';
  let lkRoom = null;
  let lkRole = 'viewer';

  async function getLiveKitToken(room, role) {
    const r = await fetch(SFU_API + '/api/livekit/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: JSON.stringify({ room, role })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Live service unavailable');
    return d;
  }

  async function connectSFU(roomId, role) {
    if (!token) throw new Error('Login required');
    if (!window.LivekitClient) throw new Error('Live video client failed to load');
    const d = await getLiveKitToken(roomId, role);
    const Room = window.LivekitClient.Room;
    const RoomEvent = window.LivekitClient.RoomEvent;
    lkRoom = new Room({ adaptiveStream: true, dynacast: true });
    lkRole = role;
    lkRoom.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
      if (track.kind !== 'video') return;
      const el = track.attach();
      el.className = 'sfu-video';
      const camera = document.getElementById('camera');
      camera.style.display = 'none';
      camera.parentElement.querySelectorAll('.sfu-video').forEach(x => x.remove());
      camera.parentElement.prepend(el);
    });
    lkRoom.on(RoomEvent.TrackUnsubscribed, track => track.detach().forEach(el => el.remove()));
    lkRoom.on(RoomEvent.Disconnected, () => { lkRoom = null; });
    await lkRoom.connect(d.url, d.token);
    if (role === 'host' || role === 'guest') {
      await lkRoom.localParticipant.setCameraEnabled(true);
      await lkRoom.localParticipant.setMicrophoneEnabled(true);
      const camera = document.getElementById('camera');
      camera.style.display = 'block';
      camera.srcObject = null;
    }
    return d;
  }

  window.addEventListener('load', () => {
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.min.js';
    s.async = true;
    document.head.appendChild(s);
  });

  const originalStart = window.startLive;
  window.startLive = async function () {
    if (!token) return (location.href = 'index.html?login=1');
    const title = document.getElementById('title').value.trim() || 'Live on REelo';
    const r = await fetch(SFU_API + '/api/live', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: JSON.stringify({ title })
    });
    const d = await r.json();
    if (!r.ok) return alert(d.detail || 'Unable to start LIVE');
    try {
      await window.openRoom(d.id, true);
      await connectSFU(d.id, 'host');
    } catch (e) { alert(e.message); }
  };

  const originalJoin = window.join;
  window.join = async function (id) {
    if (!token) return (location.href = 'index.html?login=1');
    try {
      await window.openRoom(id, false);
      await connectSFU(id, 'viewer');
    } catch (e) { alert(e.message); }
  };

  window.addEventListener('pagehide', () => { try { lkRoom?.disconnect(); } catch (_) {} });
})();
