"""Payout lifecycle helpers for REelo.

This module keeps provider-specific payment logic out of the API layer.
Actual fund movement remains disabled until a verified payment provider is configured.
"""
from __future__ import annotations

PAYOUT_STATES = {"pending", "processing", "paid", "failed", "rejected"}
TRANSITIONS = {
    "pending": {"processing", "rejected"},
    "processing": {"paid", "failed"},
    "paid": set(),
    "failed": set(),
    "rejected": set(),
}


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def normalize_state(value: str | None) -> str:
    state = (value or "").strip().lower()
    if state not in PAYOUT_STATES:
        raise ValueError("Invalid payout state")
    return state


class PaymentProvider:
    """Provider interface; implementations must be added before real transfers."""

    name = "unconfigured"

    def send_payout(self, *, request_id: str, amount_cents: int, method_type: str, identifier: str) -> dict:
        raise RuntimeError("Payment provider is not configured; no funds were transferred")
