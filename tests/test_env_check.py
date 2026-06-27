# -*- coding: utf-8 -*-
import os
import pytest


def test_validate_env_missing_token_exits(monkeypatch):
    monkeypatch.setattr(os, "environ", {"DISCORD_BOT_TOKEN": "", "GUILD_ID": "123", "PROMOTION_CH_01": "1:2", "RANKMAP_01": "x:3"})
    import sys
    from utils.env_check import validate_env
    with pytest.raises(SystemExit) as exc_info:
        validate_env()
    assert exc_info.value.code == 1


def test_validate_env_has_token_and_required_passes(monkeypatch):
    monkeypatch.setattr(os, "environ", {
        "DISCORD_BOT_TOKEN": "test_token",
        "GUILD_ID": "123456",
        "PROMOTION_CH_01": "111:222",
        "RANKMAP_01": "рядовой -> сержант:333",
    })
    from utils.env_check import validate_env
    validate_env()
