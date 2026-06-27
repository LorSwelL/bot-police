# -*- coding: utf-8 -*-
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict

import asyncio
import aiosqlite

from config import Config

logger = logging.getLogger(__name__)


def _resolve_db_path() -> str:
    if getattr(Config, "DB_PATH", ""):
        path = Config.DB_PATH
    elif getattr(Config, "DATABASE_URL", ""):
        url = Config.DATABASE_URL
        if "///" in url:
            path = url.split("///", 1)[1]
        else:
            path = "data/bot.db"
    else:
        path = "data/bot.db"

    path = (path or "").strip()
    if not path:
        path = "data/bot.db"

    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    return path


DB_PATH = _resolve_db_path()


_DB_CONN: aiosqlite.Connection | None = None
_DB_CONN_LOCK = asyncio.Lock()


async def _get_or_create_conn() -> aiosqlite.Connection:
    global _DB_CONN
    async with _DB_CONN_LOCK:
        if _DB_CONN is not None:
            try:
                await _DB_CONN.execute("SELECT 1")
            except (aiosqlite.ProgrammingError, aiosqlite.OperationalError) as e:
                err_msg = str(e).lower()
                if "closed" in err_msg or "invalid" in err_msg or "not open" in err_msg:
                    logger.warning("БД: соединение закрыто или недоступно, переподключаемся: %s", e)
                    try:
                        await _DB_CONN.close()
                    except Exception as e:
                        logger.debug("БД: ошибка при закрытии соединения: %s", e, exc_info=True)
                    _DB_CONN = None

        if _DB_CONN is None:
            conn = await aiosqlite.connect(DB_PATH)
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA foreign_keys=ON;")
            logger.info("БД: открыто новое соединение (path=%s, journal_mode=WAL, foreign_keys=ON)", DB_PATH)
            _DB_CONN = conn
        return _DB_CONN


async def close_db() -> None:
    """Закрыть глобальное соединение с БД (для тестов и корректного выхода)."""
    global _DB_CONN
    async with _DB_CONN_LOCK:
        if _DB_CONN is not None:
            await _DB_CONN.close()
            _DB_CONN = None


@asynccontextmanager
async def _get_conn():
    conn = await _get_or_create_conn()
    yield conn


async def _execute_with_retry(
    conn: aiosqlite.Connection,
    sql: str,
    params: tuple | list = (),
    *,
    retries: int = 3,
    base_delay: float = 0.1,
) -> None:
    """
    Выполнить SQL с небольшим числом повторов при транзиентных ошибках (например, database is locked).
    """
    attempt = 0
    while True:
        try:
            await conn.execute(sql, params)
            return
        except aiosqlite.OperationalError as e:
            msg = str(e).lower()
            if "database is locked" in msg and attempt < retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Повтор SQL из-за блокировки БД (попытка %s/%s): %s",
                    attempt + 1,
                    retries,
                    e,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            raise


async def init_db() -> None:
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS requests (
                message_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                data TEXT,
                created_at TEXT,
                request_type TEXT
            )
        """)
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id)")
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_requests_created_at ON requests(created_at)")
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS firing_requests (
                message_id INTEGER PRIMARY KEY,
                discord_id INTEGER,
                data TEXT,
                created_at TEXT
            )
        """)
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_firing_requests_discord_id ON firing_requests(discord_id)")
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_firing_requests_created_at ON firing_requests(created_at)")
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS promotion_requests (
                message_id INTEGER PRIMARY KEY,
                discord_id INTEGER,
                data TEXT,
                created_at TEXT
            )
        """)
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_promotion_requests_discord_id ON promotion_requests(discord_id)")
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_promotion_requests_created_at ON promotion_requests(created_at)")
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS warehouse_requests (
                message_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                data TEXT,
                created_at TEXT
            )
        """)
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_warehouse_requests_user_id ON warehouse_requests(user_id)")
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_warehouse_requests_created_at ON warehouse_requests(created_at)")
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS department_transfer_requests (
                message_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                target_dept TEXT,
                source_dept TEXT,
                from_academy INTEGER,
                data TEXT,
                approved_source INTEGER,
                approved_target INTEGER,
                created_at TEXT
            )
        """)
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_department_transfer_requests_user_id ON department_transfer_requests(user_id)")
            await _execute_with_retry(conn, "CREATE INDEX IF NOT EXISTS idx_department_transfer_requests_created_at ON department_transfer_requests(created_at)")
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS orls_draft_reports (
                user_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT
            )
        """)
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS osb_draft_reports (
                user_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT
            )
        """)
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS grom_draft_reports (
                user_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT
            )
        """)
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS pps_draft_reports (
                user_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT
            )
        """)
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS academy_draft_reports (
                user_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT
            )
        """)
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS warehouse_sessions (
                session_key TEXT PRIMARY KEY,
                items_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
            await _execute_with_retry(conn, """
            CREATE TABLE IF NOT EXISTS warehouse_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_issue_at TEXT NOT NULL
            )
        """)
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка инициализации БД")
            raise


def _validate_table_name(table: str) -> str:
    table = str(table or "").strip()
    allowed = {
        "requests",
        "firing_requests",
        "promotion_requests",
        "warehouse_requests",
        "department_transfer_requests",
    }
    if table not in allowed:
        raise ValueError(f"Unknown table: {table}")
    return table


def _validate_user_field(table: str, user_field: str) -> str:
    table = _validate_table_name(table)
    user_field = str(user_field or "").strip()
    allowed_fields = {
        "requests": {"user_id"},
        "warehouse_requests": {"user_id"},
        "firing_requests": {"discord_id"},
        "promotion_requests": {"discord_id"},
        "department_transfer_requests": {"user_id"},
    }.get(table, set())
    if user_field not in allowed_fields:
        raise ValueError(f"Invalid user_field for {table}: {user_field}")
    return user_field


async def has_request_for_user(table: str, user_field: str, user_id: int) -> bool:
    """
    Точечная проверка наличия записи по user_id/discord_id без загрузки всей таблицы.
    """
    table = _validate_table_name(table)
    user_field = _validate_user_field(table, user_field)
    user_id = int(user_id)
    if not user_id:
        return False
    async with _get_conn() as conn:
        cursor = await conn.execute(
            f"SELECT 1 FROM {table} WHERE {user_field} = ? LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
    return bool(row)


async def load_recent_requests(
    table: str,
    *,
    max_days: int | None = None,
    limit: int | None = None,
) -> Dict[int, Dict]:
    """
    Загрузить последние записи из таблицы по created_at с LIMIT, без чтения всего содержимого.
    Возвращает {message_id: data_dict}.
    """
    table = _validate_table_name(table)
    max_days_int = int(max_days) if max_days else 0
    limit_int = int(limit) if limit else 0
    where = ""
    params: list[Any] = []
    if max_days_int > 0:
        cutoff = (datetime.now() - timedelta(days=max_days_int)).isoformat()
        where = "WHERE created_at >= ?"
        params.append(cutoff)
    sql = f"SELECT message_id, data FROM {table} {where} ORDER BY created_at DESC"
    if limit_int > 0:
        sql += " LIMIT ?"
        params.append(limit_int)

    result: Dict[int, Dict] = {}
    async with _get_conn() as conn:
        cursor = await conn.execute(sql, tuple(params))
        rows = await cursor.fetchall()
    for mid, data in rows:
        try:
            result[int(mid)] = json.loads(data) if data else {}
        except (ValueError, TypeError):
            continue
        except json.JSONDecodeError as e:
            logger.warning("Пропуск битой записи в %s message_id=%s: %s", table, mid, e)
    return result


async def optimize_db(*, vacuum: bool = False) -> None:
    """
    Лёгкая оптимизация SQLite без изменения схемы:
    - PRAGMA optimize;
    - checkpoint WAL.
    VACUUM опционален и может быть дорогим/блокирующим.
    """
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(conn, "PRAGMA optimize;")
            await _execute_with_retry(conn, "PRAGMA wal_checkpoint(TRUNCATE);")
            if vacuum:
                # VACUUM нельзя выполнять внутри транзакции.
                await conn.commit()
                await conn.execute("VACUUM;")
            await conn.commit()
        except Exception:
            try:
                await conn.rollback()
            except Exception:
                pass
            logger.exception("Ошибка optimize_db(vacuum=%s)", vacuum)
            raise


async def save_request(table: str, message_id: int, data: Dict[str, Any]) -> None:
    data_json = json.dumps(data, ensure_ascii=False, default=str)
    created_at = data.get("created_at", datetime.now().isoformat())

    if table == "requests":
        if "user_id" not in data:
            logger.warning("save_request(requests): отсутствует user_id в data, message_id=%s", message_id)
            raise ValueError("requests requires 'user_id' in data")
    elif table == "firing_requests":
        if "discord_id" not in data:
            logger.warning("save_request(firing_requests): отсутствует discord_id в data, message_id=%s", message_id)
            raise ValueError("firing_requests requires 'discord_id' in data")
    elif table == "promotion_requests":
        if "discord_id" not in data:
            logger.warning("save_request(promotion_requests): отсутствует discord_id в data, message_id=%s", message_id)
            raise ValueError("promotion_requests requires 'discord_id' in data")
    elif table == "warehouse_requests":
        if "user_id" not in data:
            logger.warning("save_request(warehouse_requests): отсутствует user_id в data, message_id=%s", message_id)
            raise ValueError("warehouse_requests requires 'user_id' in data")

    async with _get_conn() as conn:
        try:
            if table == "requests":
                await _execute_with_retry(
                    conn,
                    "INSERT OR REPLACE INTO requests VALUES (?,?,?,?,?)",
                    (message_id, data["user_id"], data_json, created_at, data.get("request_type", "")),
                )
            elif table == "firing_requests":
                await _execute_with_retry(
                    conn,
                    "INSERT OR REPLACE INTO firing_requests VALUES (?,?,?,?)",
                    (message_id, data["discord_id"], data_json, created_at),
                )
            elif table == "promotion_requests":
                await _execute_with_retry(
                    conn,
                    "INSERT OR REPLACE INTO promotion_requests VALUES (?,?,?,?)",
                    (message_id, data["discord_id"], data_json, created_at),
                )
            elif table == "warehouse_requests":
                await _execute_with_retry(
                    conn,
                    "INSERT OR REPLACE INTO warehouse_requests VALUES (?,?,?,?)",
                    (message_id, data["user_id"], data_json, created_at),
                )
            else:
                raise ValueError(f"Unknown table: {table}")
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка save_request table=%s message_id=%s", table, message_id)
            raise


async def delete_request(table: str, message_id: int) -> None:
    if table not in {"requests", "firing_requests", "promotion_requests", "warehouse_requests", "department_transfer_requests"}:
        raise ValueError(f"Unknown table: {table}")
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(conn, f"DELETE FROM {table} WHERE message_id = ?", (message_id,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка delete_request table=%s message_id=%s", table, message_id)
            raise


async def _load_all(table: str) -> Dict[int, Dict]:
    result = {}
    async with _get_conn() as conn:
        cursor = await conn.execute(f"SELECT message_id, data FROM {table}")
        rows = await cursor.fetchall()
    for mid, data in rows:
        try:
            result[mid] = json.loads(data) if data else {}
        except json.JSONDecodeError as e:
            logger.warning("Пропуск битой записи в %s message_id=%s: %s", table, mid, e)
    return result


async def _draft_save_generic(table: str, user_id: int, draft: Dict[str, Any]) -> None:
    """
    Унифицированное сохранение черновика в таблицу *_draft_reports.
    """
    storable = {k: v for k, v in (draft or {}).items() if k != "_ephemeral_msg"}
    data_json = json.dumps(storable, ensure_ascii=False, default=str)
    updated_at = datetime.now().isoformat()
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(
                conn,
                f"INSERT OR REPLACE INTO {table} (user_id, data, updated_at) VALUES (?, ?, ?)",
                (user_id, data_json, updated_at),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка _draft_save_generic table=%s user_id=%s", table, user_id)
            raise


async def _draft_load_generic(table: str, user_id: int) -> Dict[str, Any] | None:
    """
    Унифицированная загрузка черновика из таблицы *_draft_reports.
    """
    async with _get_conn() as conn:
        cursor = await conn.execute(f"SELECT data FROM {table} WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
    if not row or not row[0]:
        return None
    try:
        data = json.loads(row[0])
    except json.JSONDecodeError as e:
        logger.warning("Ошибка чтения %s user_id=%s: %s", table, user_id, e)
        return None
    data["_ephemeral_msg"] = None
    data.setdefault("message_id", None)
    return data


async def _draft_delete_generic(table: str, user_id: int) -> None:
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(conn, f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка _draft_delete_generic table=%s user_id=%s", table, user_id)
            raise


async def _cleanup_old_drafts_generic(table: str, days: int) -> int:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    async with _get_conn() as conn:
        try:
            cursor = await conn.execute(f"SELECT user_id FROM {table} WHERE updated_at < ?", (cutoff,))
            to_delete = await cursor.fetchall()
            for (uid,) in to_delete:
                await _execute_with_retry(conn, f"DELETE FROM {table} WHERE user_id = ?", (uid,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка _cleanup_old_drafts_generic table=%s days=%s", table, days)
            raise
    return len(to_delete)


async def load_all_requests() -> Dict[int, Dict]:
    return await _load_all("requests")


async def load_all_firing_requests() -> Dict[int, Dict]:
    return await _load_all("firing_requests")


async def load_all_promotion_requests() -> Dict[int, Dict]:
    return await _load_all("promotion_requests")


async def load_all_warehouse_requests() -> Dict[int, Dict]:
    return await _load_all("warehouse_requests")


async def save_orls_draft(user_id: int, draft: Dict[str, Any]) -> None:
    await _draft_save_generic("orls_draft_reports", user_id, draft)


async def load_orls_draft(user_id: int) -> Dict[str, Any] | None:
    return await _draft_load_generic("orls_draft_reports", user_id)


async def delete_orls_draft(user_id: int) -> None:
    await _draft_delete_generic("orls_draft_reports", user_id)


async def cleanup_old_orls_drafts(days: int = 14) -> int:
    return await _cleanup_old_drafts_generic("orls_draft_reports", days)


async def save_osb_draft(user_id: int, draft: Dict[str, Any]) -> None:
    await _draft_save_generic("osb_draft_reports", user_id, draft)


async def load_osb_draft(user_id: int) -> Dict[str, Any] | None:
    return await _draft_load_generic("osb_draft_reports", user_id)


async def delete_osb_draft(user_id: int) -> None:
    await _draft_delete_generic("osb_draft_reports", user_id)


async def cleanup_old_osb_drafts(days: int = 14) -> int:
    return await _cleanup_old_drafts_generic("osb_draft_reports", days)


async def save_grom_draft(user_id: int, draft: Dict[str, Any]) -> None:
    await _draft_save_generic("grom_draft_reports", user_id, draft)


async def load_grom_draft(user_id: int) -> Dict[str, Any] | None:
    return await _draft_load_generic("grom_draft_reports", user_id)


async def delete_grom_draft(user_id: int) -> None:
    await _draft_delete_generic("grom_draft_reports", user_id)


async def cleanup_old_grom_drafts(days: int = 14) -> int:
    return await _cleanup_old_drafts_generic("grom_draft_reports", days)


async def save_pps_draft(user_id: int, draft: Dict[str, Any]) -> None:
    await _draft_save_generic("pps_draft_reports", user_id, draft)


async def load_pps_draft(user_id: int) -> Dict[str, Any] | None:
    return await _draft_load_generic("pps_draft_reports", user_id)


async def delete_pps_draft(user_id: int) -> None:
    await _draft_delete_generic("pps_draft_reports", user_id)


async def cleanup_old_pps_drafts(days: int = 14) -> int:
    return await _cleanup_old_drafts_generic("pps_draft_reports", days)


async def save_academy_draft(user_id: int, draft: Dict[str, Any]) -> None:
    await _draft_save_generic("academy_draft_reports", user_id, draft)


async def load_academy_draft(user_id: int) -> Dict[str, Any] | None:
    return await _draft_load_generic("academy_draft_reports", user_id)


async def delete_academy_draft(user_id: int) -> None:
    await _draft_delete_generic("academy_draft_reports", user_id)


async def cleanup_old_academy_drafts(days: int = 14) -> int:
    return await _cleanup_old_drafts_generic("academy_draft_reports", days)


async def cleanup_old_requests_db(days: int) -> None:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    async with _get_conn() as conn:
        try:
            for table in ["requests", "firing_requests", "promotion_requests", "warehouse_requests"]:
                await _execute_with_retry(conn, f"DELETE FROM {table} WHERE created_at < ?", (cutoff,))
            await _execute_with_retry(conn, "DELETE FROM department_transfer_requests WHERE created_at < ?", (cutoff,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка cleanup_old_requests_db days=%s", days)
            raise


async def cleanup_old_requests(days: int) -> None:
    await cleanup_old_requests_db(days)


async def cleanup_old_firing_requests(days: int) -> None:
    await cleanup_old_requests_db(days)


async def cleanup_old_promotion_requests(days: int) -> None:
    await cleanup_old_requests_db(days)


async def cleanup_old_warehouse_requests(days: int) -> None:
    await cleanup_old_requests_db(days)


async def save_user_request(message_id: int, data: dict) -> None:
    await save_request("requests", message_id, data)


async def delete_user_request(message_id: int) -> None:
    await delete_request("requests", message_id)


async def save_firing_request(message_id: int, data: dict) -> None:
    await save_request("firing_requests", message_id, data)


async def delete_firing_request(message_id: int) -> None:
    await delete_request("firing_requests", message_id)


async def save_promotion_request(message_id: int, data: dict) -> None:
    await save_request("promotion_requests", message_id, data)


async def delete_promotion_request(message_id: int) -> None:
    await delete_request("promotion_requests", message_id)


async def save_warehouse_request(message_id: int, data: dict) -> None:
    await save_request("warehouse_requests", message_id, data)


async def delete_warehouse_request(message_id: int) -> None:
    await delete_request("warehouse_requests", message_id)


async def save_department_transfer_request(message_id: int, payload: Dict[str, Any]) -> None:
    data_json = json.dumps(payload.get("data", {}), ensure_ascii=False, default=str)
    from_academy = 1 if payload.get("from_academy") else 0
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(
                conn,
                """INSERT OR REPLACE INTO department_transfer_requests
               (message_id, user_id, target_dept, source_dept, from_academy, data, approved_source, approved_target, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message_id,
                    int(payload.get("user_id", 0)),
                    str(payload.get("target_dept", "")),
                    str(payload.get("source_dept", "")),
                    from_academy,
                    data_json,
                    int(payload.get("approved_source", 0)),
                    int(payload.get("approved_target", 0)),
                    payload.get("created_at", datetime.now().isoformat()),
                ),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка save_department_transfer_request message_id=%s", message_id)
            raise


async def update_department_transfer_approval(
    message_id: int,
    *,
    approved_source: int | None = None,
    approved_target: int | None = None,
) -> None:
    async with _get_conn() as conn:
        try:
            if approved_source is not None:
                await _execute_with_retry(
                    conn,
                    "UPDATE department_transfer_requests SET approved_source = ? WHERE message_id = ?",
                    (approved_source, message_id),
                )
            if approved_target is not None:
                await _execute_with_retry(
                    conn,
                    "UPDATE department_transfer_requests SET approved_target = ? WHERE message_id = ?",
                    (approved_target, message_id),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка update_department_transfer_approval message_id=%s", message_id)
            raise


async def load_department_transfer_request(message_id: int) -> Dict[str, Any] | None:
    async with _get_conn() as conn:
        cursor = await conn.execute(
            """SELECT user_id, target_dept, source_dept, from_academy, data, approved_source, approved_target, created_at
               FROM department_transfer_requests WHERE message_id = ?""",
            (message_id,),
        )
        row = await cursor.fetchone()
    if not row:
        return None
    data = {}
    if row[4]:
        try:
            data = json.loads(row[4])
        except json.JSONDecodeError:
            pass
    return {
        "message_id": message_id,
        "user_id": row[0],
        "target_dept": row[1],
        "source_dept": row[2],
        "from_academy": bool(row[3]),
        "data": data,
        "approved_source": row[5] or 0,
        "approved_target": row[6] or 0,
        "created_at": row[7],
    }


async def delete_department_transfer_request(message_id: int) -> None:
    await delete_request("department_transfer_requests", message_id)


async def load_all_department_transfer_requests() -> Dict[int, Dict[str, Any]]:
    result = {}
    async with _get_conn() as conn:
        cursor = await conn.execute(
            """SELECT message_id, user_id, target_dept, source_dept, from_academy, data, approved_source, approved_target, created_at
               FROM department_transfer_requests"""
        )
        rows = await cursor.fetchall()
    for r in rows:
        try:
            data = json.loads(r[5]) if r[5] else {}
        except json.JSONDecodeError as e:
            logger.warning("Пропуск битой записи department_transfer message_id=%s: %s", r[0], e)
            continue
        result[r[0]] = {
            "message_id": r[0],
            "user_id": r[1],
            "target_dept": r[2],
            "source_dept": r[3],
            "from_academy": bool(r[4]),
            "data": data,
            "approved_source": r[6] or 0,
            "approved_target": r[7] or 0,
            "created_at": r[8],
        }
    return result


def _session_key_to_str(session_key: Any) -> str:
    if isinstance(session_key, str):
        return session_key
    return str(session_key)


async def warehouse_session_get(session_key: Any) -> tuple[list, datetime]:
    key = _session_key_to_str(session_key)
    async with _get_conn() as conn:
        cursor = await conn.execute(
            "SELECT items_json, created_at FROM warehouse_sessions WHERE session_key = ?",
            (key,),
        )
        row = await cursor.fetchone()
    if not row:
        return [], datetime.now()
    try:
        items = json.loads(row[0]) if row[0] else []
        created = datetime.fromisoformat(row[1]) if row[1] else datetime.now()
        return items, created
    except (json.JSONDecodeError, ValueError):
        return [], datetime.now()


async def warehouse_session_set(session_key: Any, items: list, created_at: datetime | None = None) -> None:
    key = _session_key_to_str(session_key)
    created = created_at or datetime.now()
    items_json = json.dumps(items, ensure_ascii=False, default=str)
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(
                conn,
                "INSERT OR REPLACE INTO warehouse_sessions (session_key, items_json, created_at) VALUES (?, ?, ?)",
                (key, items_json, created.isoformat()),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка warehouse_session_set session_key=%s", key)
            raise


async def warehouse_session_delete(session_key: Any) -> None:
    key = _session_key_to_str(session_key)
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(conn, "DELETE FROM warehouse_sessions WHERE session_key = ?", (key,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка warehouse_session_delete session_key=%s", key)
            raise


async def warehouse_cooldown_get_all() -> Dict[int, datetime]:
    result = {}
    async with _get_conn() as conn:
        cursor = await conn.execute("SELECT user_id, last_issue_at FROM warehouse_cooldowns")
        rows = await cursor.fetchall()
    for user_id, last_at in rows:
        try:
            result[int(user_id)] = datetime.fromisoformat(last_at) if last_at else datetime.now()
        except (ValueError, TypeError):
            continue
    return result


async def warehouse_cooldown_set(user_id: int, last_issue_at: datetime) -> None:
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(
                conn,
                "INSERT OR REPLACE INTO warehouse_cooldowns (user_id, last_issue_at) VALUES (?, ?)",
                (user_id, last_issue_at.isoformat()),
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка warehouse_cooldown_set user_id=%s", user_id)
            raise


async def warehouse_cooldown_clear(user_id: int) -> None:
    async with _get_conn() as conn:
        try:
            await _execute_with_retry(conn, "DELETE FROM warehouse_cooldowns WHERE user_id = ?", (user_id,))
            await conn.commit()
        except Exception:
            await conn.rollback()
            logger.exception("Ошибка warehouse_cooldown_clear user_id=%s", user_id)
            raise


async def warehouse_session_get_all() -> Dict[str, Dict[str, Any]]:
    result = {}
    async with _get_conn() as conn:
        cursor = await conn.execute("SELECT session_key, items_json, created_at FROM warehouse_sessions")
        rows = await cursor.fetchall()
    for key, items_json, created_at in rows:
        try:
            items = json.loads(items_json) if items_json else []
            created = datetime.fromisoformat(created_at) if created_at else datetime.now()
            result[str(key)] = {"items": items, "created_at": created}
        except (json.JSONDecodeError, ValueError):
            continue
    return result