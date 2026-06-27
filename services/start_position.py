import logging
from .start_position_manager import StartPositionManager as _NewStartPositionManager

logger = logging.getLogger(__name__)


class StartPositionManager(_NewStartPositionManager):
    def __init__(self, bot):
        logger.warning(
            "⚠️ Используется legacy-модуль services.start_position. "
            "Рекомендуется импортировать services.start_position_manager"
        )
        super().__init__(bot)