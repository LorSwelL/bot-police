# -*- coding: utf-8 -*-
from typing import Any, Dict

APPROVED_SOURCE = "approved_source"
APPROVED_TARGET = "approved_target"
FROM_ACADEMY = "from_academy"

STATE_PENDING_SOURCE = "pending_source"
STATE_PENDING_TARGET = "pending_target"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"


def get_state(payload: Dict[str, Any]) -> str:
    if not payload:
        return STATE_REJECTED
    approved_src = int(payload.get(APPROVED_SOURCE) or 0)
    approved_tgt = int(payload.get(APPROVED_TARGET) or 0)
    from_academy = bool(payload.get(FROM_ACADEMY))

    if approved_src and approved_tgt:
        return STATE_APPROVED
    if approved_src:
        return STATE_PENDING_TARGET
    if from_academy:
        return STATE_PENDING_TARGET
    return STATE_PENDING_SOURCE


def can_approve_source(payload: Dict[str, Any]) -> bool:
    return get_state(payload) == STATE_PENDING_SOURCE


def can_approve_target(payload: Dict[str, Any]) -> bool:
    return get_state(payload) == STATE_PENDING_TARGET


def apply_transition(
    payload: Dict[str, Any],
    action: str,
    value: int,
) -> Dict[str, Any] | None:
    state = get_state(payload)
    out = dict(payload)

    if action == "approve_source":
        if not can_approve_source(payload):
            return None
        out[APPROVED_SOURCE] = value
        return out

    if action == "approve_target":
        if not can_approve_target(payload):
            return None
        out[APPROVED_TARGET] = value
        return out

    if action == "reject":
        if state == STATE_APPROVED:
            return None
        return None  # Запись удаляется из БД — «rejected» не храним в payload

    return None
