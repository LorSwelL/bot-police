# -*- coding: utf-8 -*-
import importlib.util
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
_spec_dt = importlib.util.spec_from_file_location(
    "department_transfer_fsm",
    _project_root / "services" / "department_transfer_fsm.py",
)
_spec_f = importlib.util.spec_from_file_location(
    "firing_fsm",
    _project_root / "services" / "firing_fsm.py",
)
_spec_p = importlib.util.spec_from_file_location(
    "promotion_fsm",
    _project_root / "services" / "promotion_fsm.py",
)
_department_transfer_fsm = importlib.util.module_from_spec(_spec_dt)
_firing_fsm = importlib.util.module_from_spec(_spec_f)
_promotion_fsm = importlib.util.module_from_spec(_spec_p)
_spec_dt.loader.exec_module(_department_transfer_fsm)
_spec_f.loader.exec_module(_firing_fsm)
_spec_p.loader.exec_module(_promotion_fsm)

import pytest

get_state = _department_transfer_fsm.get_state
can_approve_source = _department_transfer_fsm.can_approve_source
can_approve_target = _department_transfer_fsm.can_approve_target
apply_transition = _department_transfer_fsm.apply_transition
STATE_PENDING_SOURCE = _department_transfer_fsm.STATE_PENDING_SOURCE
STATE_PENDING_TARGET = _department_transfer_fsm.STATE_PENDING_TARGET
STATE_APPROVED = _department_transfer_fsm.STATE_APPROVED
STATE_REJECTED = _department_transfer_fsm.STATE_REJECTED
firing_get_state = _firing_fsm.get_state
firing_can_approve = _firing_fsm.can_approve
promotion_get_state = _promotion_fsm.get_state
promotion_can_approve = _promotion_fsm.can_approve


def test_department_transfer_get_state_empty():
    assert get_state(None) == STATE_REJECTED
    assert get_state({}) == STATE_REJECTED


def test_department_transfer_get_state_pending_source():
    assert get_state({"approved_source": 0, "approved_target": 0, "from_academy": False}) == STATE_PENDING_SOURCE


def test_department_transfer_get_state_pending_target():
    assert get_state({"approved_source": 123, "approved_target": 0}) == STATE_PENDING_TARGET


def test_department_transfer_get_state_from_academy():
    assert get_state({"approved_source": 0, "approved_target": 0, "from_academy": True}) == STATE_PENDING_TARGET


def test_department_transfer_get_state_approved():
    assert get_state({"approved_source": 1, "approved_target": 2}) == STATE_APPROVED


def test_department_transfer_can_approve_source():
    assert can_approve_source({"approved_source": 0, "approved_target": 0, "from_academy": False}) is True
    assert can_approve_source({"approved_source": 1, "approved_target": 0}) is False
    assert can_approve_source({"approved_source": 1, "approved_target": 1}) is False


def test_department_transfer_can_approve_target():
    assert can_approve_target({"approved_source": 1, "approved_target": 0}) is True
    assert can_approve_target({"approved_source": 0, "approved_target": 0, "from_academy": True}) is True
    assert can_approve_target({"approved_source": 0, "approved_target": 0, "from_academy": False}) is False
    assert can_approve_target({"approved_source": 1, "approved_target": 1}) is False


def test_department_transfer_apply_approve_source():
    payload = {"approved_source": 0, "approved_target": 0, "from_academy": False}
    out = apply_transition(payload, "approve_source", 100)
    assert out is not None
    assert out["approved_source"] == 100
    assert out["approved_target"] == 0


def test_department_transfer_apply_approve_source_invalid():
    payload = {"approved_source": 1, "approved_target": 0}
    assert apply_transition(payload, "approve_source", 100) is None


def test_department_transfer_apply_approve_target():
    payload = {"approved_source": 1, "approved_target": 0, "from_academy": False}
    out = apply_transition(payload, "approve_target", 200)
    assert out is not None
    assert out["approved_source"] == 1
    assert out["approved_target"] == 200


def test_department_transfer_apply_approve_target_invalid():
    payload = {"approved_source": 0, "approved_target": 0, "from_academy": False}
    assert apply_transition(payload, "approve_target", 200) is None


def test_firing_get_state():
    assert firing_get_state({"discord_id": 1}) == "pending"
    assert firing_get_state(None) == "rejected"
    assert firing_get_state({}) == "rejected"


def test_firing_can_approve():
    assert firing_can_approve({"discord_id": 1}) is True
    assert firing_can_approve(None) is False
    assert firing_can_approve({}) is False


def test_promotion_get_state():
    assert promotion_get_state({"discord_id": 1}) == "pending"
    assert promotion_get_state(None) == "rejected"
    assert promotion_get_state({}) == "rejected"


def test_promotion_can_approve():
    assert promotion_can_approve({"discord_id": 1}) is True
    assert promotion_can_approve(None) is False
    assert promotion_can_approve({}) is False
