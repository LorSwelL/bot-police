# -*- coding: utf-8 -*-
import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def minimal_env_for_imports():
    env = {
        "DISCORD_BOT_TOKEN": "test_token",
        "GUILD_ID": "1",
        "PROMOTION_CH_01": "1:2",
        "RANKMAP_01": "test:3",
    }
    for k, v in env.items():
        if k not in os.environ:
            os.environ[k] = v


@pytest.fixture(autouse=True, scope="session")
async def close_db_after_tests():
    """Закрыть соединение с БД после всех тестов, чтобы процесс не висел при выходе."""
    yield
    try:
        import database
        if hasattr(database, "close_db"):
            await database.close_db()
    except Exception:
        pass
