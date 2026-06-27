import logging
from .warehouse_position_manager import WarehousePositionManager as _NewWarehousePositionManager

logger = logging.getLogger(__name__)


class ButtonPositionManager(_NewWarehousePositionManager):
    def __init__(self, bot):
        logger.warning(
            "⚠️ Используется legacy-модуль services.button_position. "
            "Рекомендуется импортировать services.warehouse_position_manager"
        )
        super().__init__(bot)