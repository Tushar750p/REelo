from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set

from main import current_user

router = APIRouter(tags=["live-websocket"])

rooms: Dict[str, Set[WebSocket]] = {}


async def broadcast(room_id: str, payload: dict, sender: WebSocket | None = None):
    peers = list(rooms.get(room_id, set()))
    dead = []
    for peer in peers:
        if peer is sender:
            continue
        try:
            await peer.send_json(payload)
        except Exception:
            dead.append(peer)
    for peer in dead:
        rooms.get(room_id, set()).discard(peer)


@router.websocket("/api/live/ws/{room_id}")
async def live_socket(websocket: WebSocket, room_id: str):
    token = websocket.query_params.get("token", "")
    uid = current_user("Bearer " + token) if token else None
    if not uid:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    rooms.setdefault(room_id, set()).add(websocket)
    try:
        await websocket.send_json({"type": "ready", "user_id": uid})
        while True:
            message = await websocket.receive_json()
            kind = str(message.get("type", ""))
            if kind in {"offer", "answer", "ice", "peer-join", "peer-leave"}:
                message["from"] = uid
                await broadcast(room_id, message, sender=websocket)
    except WebSocketDisconnect:
        pass
    finally:
        rooms.get(room_id, set()).discard(websocket)
        if not rooms.get(room_id):
            rooms.pop(room_id, None)
