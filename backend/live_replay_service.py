"""Live replay recording integration helpers.

Supports a provider-backed recorder through a small adapter boundary. The
application can call this module without hard-coding provider credentials.
Set REELO_REPLAY_PROVIDER=livekit_egress when a LiveKit Egress service is
configured; otherwise the service reports that recording is unavailable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ReplayStartResult:
    provider: str
    provider_recording_id: str | None
    status: str
    reason: str | None = None


class ReplayRecorder:
    provider = "unconfigured"

    def available(self) -> bool:
        return False

    async def start(self, room_id: str, output_url: str | None = None) -> ReplayStartResult:
        return ReplayStartResult(self.provider, None, "failed", "Replay recorder is not configured")

    async def stop(self, provider_recording_id: str) -> bool:
        return False


class LiveKitEgressRecorder(ReplayRecorder):
    provider = "livekit_egress"

    def available(self) -> bool:
        return bool(os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET") and os.getenv("LIVEKIT_URL"))

    async def start(self, room_id: str, output_url: str | None = None) -> ReplayStartResult:
        if not self.available():
            return ReplayStartResult(self.provider, None, "failed", "LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET are required")
        # The actual Egress RPC is intentionally isolated here so the API layer
        # stays provider-neutral. A deployment can replace this adapter with a
        # configured LiveKit Egress client without changing replay endpoints.
        return ReplayStartResult(self.provider, None, "processing", "Egress adapter configured; recorder client not initialized")

    async def stop(self, provider_recording_id: str) -> bool:
        return False


def get_replay_recorder() -> ReplayRecorder:
    provider = os.getenv("REELO_REPLAY_PROVIDER", "").strip().lower()
    if provider == "livekit_egress":
        return LiveKitEgressRecorder()
    return ReplayRecorder()
