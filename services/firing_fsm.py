# -*- coding: utf-8 -*-
from typing import Any, Dict

STATE_PENDING = "pending"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"


def get_state(payload: Dict[str, Any]) -> str:
    if not payload:
        return STATE_REJECTED
    return STATE_PENDING


def can_approve(payload: Dict[str, Any]) -> bool:
    return get_state(payload) == STATE_PENDING


def can_reject(payload: Dict[str, Any]) -> bool:
    return get_state(payload) == STATE_PENDING
