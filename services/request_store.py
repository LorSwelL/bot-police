from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional

import logging

from database import (
    save_request,
    delete_request,
    load_all_requests,
    load_all_firing_requests,
    load_all_promotion_requests,
    load_all_warehouse_requests,
    has_request_for_user,
    load_recent_requests,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().isoformat()


@dataclass(slots=True)
class _StoreConfig:
    table: str
    user_id_field: str


class BaseRequestStore:
    """
    Базовый Store для «активных» заявок.

    Хранит ссылку на in‑memory словарь (из state) и знает,
    в какой таблице и под каким полем user_id лежат данные в БД.
    """

    def __init__(self, storage: Dict[int, Dict[str, Any]], config: _StoreConfig) -> None:
        self._storage = storage
        self._config = config

    # ---- публичный API ----

    def get_by_message_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        return self._storage.get(int(message_id))

    def iter_all(self) -> Iterable[tuple[int, Dict[str, Any]]]:
        return self._storage.items()

    async def get_active_for_user(self, user_id: int) -> list[Dict[str, Any]]:
        field = self._config.user_id_field
        return [data for data in self._storage.values() if (data or {}).get(field) == user_id]

    async def has_active_for_user(self, user_id: int) -> bool:
        """
        Проверка наличия активной заявки:
        - сначала по памяти;
        - при отсутствии — точечная проверка по БД без загрузки всей таблицы.
        """
        user_id = int(user_id)
        field = self._config.user_id_field

        for data in self._storage.values():
            if (data or {}).get(field) == user_id:
                return True

        try:
            return await has_request_for_user(self._config.table, field, user_id)
        except Exception as e:
            logger.warning(
                "Store(%s).has_active_for_user: ошибка точечной проверки в БД для user_id=%s: %s",
                self._config.table,
                user_id,
                e,
                exc_info=True,
            )
            return False

    async def upsert_active(self, message_id: int, payload: Dict[str, Any]) -> None:
        """
        Атомарное обновление: сначала БД, при успехе — память.
        При ошибке сохранения в БД память не меняется.
        """
        message_id = int(message_id)
        data = dict(payload or {})
        data.setdefault("created_at", data.get("created_at") or _now_iso())

        try:
            await save_request(self._config.table, message_id, data)
        except Exception as e:
            logger.error(
                "Store(%s).upsert_active: ошибка сохранения в БД message_id=%s: %s",
                self._config.table,
                message_id,
                e,
                exc_info=True,
            )
            raise
        self._storage[message_id] = data

    async def remove_active(self, message_id: int) -> None:
        """
        Удаление из БД, при успехе — из памяти.
        При ошибке удаления в БД память не меняется.
        """
        message_id = int(message_id)
        try:
            await delete_request(self._config.table, message_id)
        except Exception as e:
            logger.warning(
                "Store(%s).remove_active: не удалось удалить запись из БД message_id=%s: %s",
                self._config.table,
                message_id,
                e,
                exc_info=True,
            )
            raise
        self._storage.pop(message_id, None)

    async def list_for_restore(
        self,
        max_days: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Dict[int, Dict[str, Any]]:
        """
        Базовая реализация для восстановления View.

        Использует ограниченную выборку из БД по created_at и LIMIT,
        чтобы не загружать всю таблицу в память.
        """
        try:
            return await load_recent_requests(self._config.table, max_days=max_days, limit=limit)
        except Exception as e:
            logger.error(
                "Store(%s).list_for_restore: ошибка load_recent_requests: %s",
                self._config.table,
                e,
                exc_info=True,
            )
            # Фолбэк на старое поведение, но постараемся всё же ограничить объём.
            try:
                loader = {
                    "requests": load_all_requests,
                    "firing_requests": load_all_firing_requests,
                    "promotion_requests": load_all_promotion_requests,
                    "warehouse_requests": load_all_warehouse_requests,
                }.get(self._config.table)
                if loader is None:
                    return {}
                all_items = await loader()
            except Exception:
                return {}

            cutoff: Optional[datetime] = None
            if max_days and max_days > 0:
                cutoff = datetime.now() - timedelta(days=max_days)

            prepared: list[tuple[int, Dict[str, Any], datetime]] = []
            for mid, raw in (all_items or {}).items():
                data = dict(raw or {})
                created_raw = data.get("created_at")
                if isinstance(created_raw, str):
                    try:
                        created_dt = datetime.fromisoformat(created_raw)
                    except (ValueError, TypeError):
                        created_dt = datetime.min
                elif isinstance(created_raw, datetime):
                    created_dt = created_raw
                else:
                    created_dt = datetime.min
                if cutoff is not None and created_dt is not datetime.min and created_dt < cutoff:
                    continue
                try:
                    mid_int = int(mid)
                except (TypeError, ValueError):
                    continue
                prepared.append((mid_int, data, created_dt))

            prepared.sort(key=lambda t: t[2], reverse=True)
            if limit is not None and limit > 0 and len(prepared) > limit:
                prepared = prepared[:limit]
            return {mid: data for mid, data, _ in prepared}


class UserRequestStore(BaseRequestStore):
    def __init__(self, storage: Dict[int, Dict[str, Any]]) -> None:
        super().__init__(storage, _StoreConfig(table="requests", user_id_field="user_id"))


class FiringRequestStore(BaseRequestStore):
    def __init__(self, storage: Dict[int, Dict[str, Any]]) -> None:
        super().__init__(storage, _StoreConfig(table="firing_requests", user_id_field="discord_id"))


class PromotionRequestStore(BaseRequestStore):
    def __init__(self, storage: Dict[int, Dict[str, Any]]) -> None:
        super().__init__(storage, _StoreConfig(table="promotion_requests", user_id_field="discord_id"))


class WarehouseRequestStore(BaseRequestStore):
    def __init__(self, storage: Dict[int, Dict[str, Any]]) -> None:
        super().__init__(storage, _StoreConfig(table="warehouse_requests", user_id_field="user_id"))

