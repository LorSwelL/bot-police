# -*- coding: utf-8 -*-
import asyncio
import os
import tempfile
import pytest


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.mark.asyncio
async def test_init_db_creates_tables(temp_db_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", temp_db_path)

    await database.init_db()

    assert os.path.isfile(temp_db_path)
    async with database._get_conn() as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='requests'"
        )
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "requests"

    # Закрываем соединение с БД, чтобы на Windows можно было удалить файл temp_db_path
    await database.close_db()
