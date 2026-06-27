from typing import Dict, List, Any, Tuple, Hashable
from datetime import datetime, timedelta
import logging
import asyncio
from data.warehouse_items import WAREHOUSE_ITEMS

logger = logging.getLogger(__name__)

user_sessions: Dict[Hashable, Dict[str, Any]] = {}
_session_lock = asyncio.Lock()


def _normalize_key(session_key: Hashable) -> Hashable | None:
    if session_key in user_sessions:
        return session_key
    if str(session_key) in user_sessions:
        return str(session_key)
    return None


class WarehouseSession:
    @staticmethod
    async def load_sessions_into_memory(sessions_dict: Dict[str, Dict[str, Any]]) -> None:
        async with _session_lock:
            user_sessions.clear()
            for key, data in sessions_dict.items():
                user_sessions[key] = {
                    "items": list((data.get("items") or [])),
                    "created_at": data.get("created_at") or datetime.now(),
                }
        if sessions_dict:
            logger.info("WarehouseSession: загружено %s сессий из БД", len(sessions_dict))

    @staticmethod
    async def purge_expired(max_age_hours: int = 24) -> int:
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        to_delete = []
        async with _session_lock:
            for key, session in list(user_sessions.items()):
                created = session.get("created_at")
                if isinstance(created, datetime) and created < cutoff:
                    to_delete.append(key)
            for key in to_delete:
                user_sessions.pop(key, None)
        if to_delete:
            logger.info("🧹 WarehouseSession: очищено %s старых сессий", len(to_delete))
        return len(to_delete)

    @staticmethod
    async def get_session(session_key: Hashable) -> Dict[str, Any]:
        await WarehouseSession.purge_expired(24)
        async with _session_lock:
            key = _normalize_key(session_key)
            if key is not None:
                return user_sessions[key]
            user_sessions[session_key] = {
                "items": [],
                "created_at": datetime.now(),
            }
            return user_sessions[session_key]

    @staticmethod
    async def set_items(session_key: Hashable, items: List[Dict[str, Any]]):
        session = await WarehouseSession.get_session(session_key)
        session["items"] = [dict(item) for item in (items or [])]
        try:
            from services.worker_queue import get_worker
            from database import warehouse_session_set
            await get_worker().submit(
                warehouse_session_set, session_key, session["items"], session.get("created_at")
            )
        except Exception as e:
            logger.warning(
                "WarehouseSession persist set_items failed for session_key=%r: %s",
                session_key,
                e,
                exc_info=True,
            )

    @staticmethod
    async def add_item(session_key: Hashable, category: str, item_name: str, quantity: int) -> Tuple[bool, str]:
        session = await WarehouseSession.get_session(session_key)

        category_data = WAREHOUSE_ITEMS[category]
        item_limit = category_data["items"][item_name]

        if isinstance(item_limit, dict):
            max_item = int(item_limit.get("max", 0))
        else:
            max_item = int(item_limit)

        current_qty = 0
        for item in session["items"]:
            if item.get("category") == category and item.get("item") == item_name:
                try:
                    current_qty += int(item.get("quantity", 0))
                except (TypeError, ValueError):
                    continue

        if current_qty + quantity > max_item:
            return False, f"❌ Нельзя взять больше **{max_item}** {item_name} в один запрос!"

        if "max_total" in category_data:
            total_in_category = 0
            for item in session["items"]:
                if item.get("category") == category:
                    try:
                        total_in_category += int(item.get("quantity", 0))
                    except (TypeError, ValueError):
                        continue

            max_total = int(category_data["max_total"])
            if total_in_category + quantity > max_total:
                return False, f"❌ Нельзя взять больше **{max_total}** предметов в категории {category}!"

        session["items"].append({
            "category": category,
            "item": item_name,
            "quantity": quantity,
        })

        try:
            from services.worker_queue import get_worker
            from database import warehouse_session_set
            await get_worker().submit(
                warehouse_session_set, session_key, session["items"], session.get("created_at")
            )
        except Exception as e:
            logger.warning(
                "WarehouseSession persist add_item failed for session_key=%r, item=%r: %s",
                session_key,
                {"category": category, "item": item_name, "quantity": quantity},
                e,
                exc_info=True,
            )
        return True, ""

    @staticmethod
    async def get_items(session_key: Hashable) -> List[Dict[str, Any]]:
        session = await WarehouseSession.get_session(session_key)
        return session["items"]

    @staticmethod
    async def clear_session(session_key: Hashable):
        async with _session_lock:
            key = _normalize_key(session_key)
            k = key if key in user_sessions else str(session_key)
            if k in user_sessions:
                user_sessions.pop(k, None)
            if session_key in user_sessions:
                user_sessions.pop(session_key, None)
        try:
            from services.worker_queue import get_worker
            from database import warehouse_session_delete
            await get_worker().submit(warehouse_session_delete, session_key)
        except Exception as e:
            logger.warning(
                "WarehouseSession delete persist failed for session_key=%r: %s",
                session_key,
                e,
                exc_info=True,
            )

    @staticmethod
    async def remove_item(session_key: Hashable, index: int) -> bool:
        session = await WarehouseSession.get_session(session_key)
        if 0 <= index < len(session["items"]):
            session["items"].pop(index)
            try:
                from services.worker_queue import get_worker
                from database import warehouse_session_set
                await get_worker().submit(
                    warehouse_session_set, session_key, session["items"], session.get("created_at")
                )
            except Exception as e:
                logger.warning(
                    "WarehouseSession persist remove_item failed for session_key=%r, index=%s: %s",
                    session_key,
                    index,
                    e,
                    exc_info=True,
                )
            return True
        return False