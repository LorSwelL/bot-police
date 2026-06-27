# -*- coding: utf-8 -*-
import pytest
from datetime import datetime

WAREHOUSE_ITEMS_MOCK = {
    "weapons": {
        "items": {"pistol": 1},
        "max_total": 10,
    },
}


@pytest.fixture
def warehouse_items_mock(monkeypatch):
    import data.warehouse_items as wh_data
    monkeypatch.setattr(wh_data, "WAREHOUSE_ITEMS", WAREHOUSE_ITEMS_MOCK)


@pytest.mark.asyncio
async def test_warehouse_session_get_session_creates_new(warehouse_items_mock):
    from services.warehouse_session import WarehouseSession, user_sessions
    from services import warehouse_session as ws_mod
    async with ws_mod._session_lock:
        user_sessions.clear()
    session = await WarehouseSession.get_session(99999)
    assert session["items"] == []
    assert "created_at" in session
    async with ws_mod._session_lock:
        assert 99999 in user_sessions or "99999" in user_sessions


@pytest.mark.asyncio
async def test_warehouse_session_add_item_appends(warehouse_items_mock):
    from services.warehouse_session import WarehouseSession, user_sessions
    import asyncio
    from services import warehouse_session as ws_mod
    async with ws_mod._session_lock:
        user_sessions.clear()
    key = 88888
    ok, msg = await WarehouseSession.add_item(key, "weapons", "pistol", 1)
    assert ok is True
    assert msg == ""
    items = await WarehouseSession.get_items(key)
    assert len(items) == 1
    assert items[0]["category"] == "weapons" and items[0]["item"] == "pistol" and items[0]["quantity"] == 1
