import json
import logging
from pathlib import Path
from typing import Any, Dict, Mapping

from config import Config

logger = logging.getLogger(__name__)


class WarehouseCatalog:
    """
    Централизованный доступ к ассортименту склада.

    Сейчас фактически используется только статический источник из data.warehouse_items,
    но структура класса позволяет в будущем безболезненно переключиться на JSON/БД.
    """

    _cache: Dict[str, Any] | None = None

    @classmethod
    def _load_static(cls) -> Dict[str, Any]:
        from data.warehouse_items import WAREHOUSE_ITEMS

        # Возвращаем копию, чтобы не дать внешнему коду мутировать исходный словарь.
        return dict(WAREHOUSE_ITEMS)

    @classmethod
    def _load_from_json(cls, path: str | None) -> Dict[str, Any]:
        if not path:
            logger.warning(
                "WAREHOUSE_CATALOG_SOURCE=json, но путь к JSON не задан. Используется статический ассортимент."
            )
            return cls._load_static()
        try:
            content = Path(path).read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("Ожидался объект с категориями склада")
            return data
        except Exception as e:
            logger.error(
                "Не удалось загрузить ассортимент склада из JSON (%s): %s. Используется статический ассортимент.",
                path,
                e,
                exc_info=True,
            )
            return cls._load_static()

    @classmethod
    def _load_from_db(cls) -> Dict[str, Any]:
        # Заглушка под будущую реализацию.
        logger.warning(
            "WAREHOUSE_CATALOG_SOURCE=db ещё не реализован. Используется статический ассортимент."
        )
        return cls._load_static()

    @classmethod
    def _load(cls) -> Dict[str, Any]:
        source = (Config.WAREHOUSE_CATALOG_SOURCE or "static").lower()
        if source == "static":
            return cls._load_static()
        if source == "json":
            json_path = getattr(Config, "WAREHOUSE_CATALOG_JSON_PATH", None)
            return cls._load_from_json(json_path)
        if source == "db":
            return cls._load_from_db()

        logger.warning(
            "Неизвестный WAREHOUSE_CATALOG_SOURCE=%s. Ожидается static|json|db. Используется static.",
            source,
        )
        return cls._load_static()

    @classmethod
    def get_catalog(cls) -> Mapping[str, Any]:
        if cls._cache is None:
            cls._cache = cls._load()
        return cls._cache

