#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import time
import asyncio
from dotenv import load_dotenv
load_dotenv()

from utils.env_check import validate_env
validate_env()

import discord
from discord.ext import commands
import logging
from logging.handlers import RotatingFileHandler

import state
from config import Config

# Задержка перед переподключением к Discord при ошибке/потере связи (секунды)
RECONNECT_DELAY_SEC = 15
# Таймаут ожидания завершения фоновых задач при shutdown (секунды)
SHUTDOWN_TASKS_TIMEOUT_SEC = 5

file_handler = RotatingFileHandler(
    Config.LOG_FILE,
    maxBytes=2 * 1024 * 1024,  # 2 MB
    backupCount=5,
    encoding="utf-8",
)

logging.basicConfig(
    level=Config.LOG_LEVEL,
    format=Config.LOG_FORMAT,
    handlers=[
        file_handler,
        logging.StreamHandler(),
    ],
)
# Бот не использует голос — скрываем предупреждение о PyNaCl
logging.getLogger("discord.client").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

from services.log_alerts import setup_log_alerts

setup_log_alerts()

intents = discord.Intents.default()
intents.message_content = Config.ENABLE_MESSAGE_CONTENT_INTENT
intents.members = True

# Модули, зависящие от бота (импорты после создания intents)
from services.cache import ChannelCache, RoleCache
from services.cleanup import CleanupManager
from services.firing_position_manager import FiringPositionManager
from services.position_apply_academy import AcademyApplyPositionManager
from services.position_apply_grom import ApplyGromPositionManager
from services.position_apply_orls import ApplyOrlsPositionManager
from services.position_apply_osb import ApplyOsbPositionManager
from services.position_apply_pps import ApplyPpsPositionManager
from services.position_admin_transfer import AdminTransferPositionManager
from services.request_store import (
    UserRequestStore,
    FiringRequestStore,
    PromotionRequestStore,
    WarehouseRequestStore,
)
from services.restore_views import ViewRestorer
from services.start_position_manager import StartPositionManager
from services.warehouse_position_manager import WarehousePositionManager
from services.worker_queue import get_worker, init_worker
from events import register_events
from commands.admin import register_admin_commands
from commands.promotion_setup import register_promotion_setup_commands


def _stop_worker_and_tasks() -> list:
    """Остановить воркер очереди и отменить фоновые задачи (перед переподключением или выходом).
    
    Возвращает список отменённых задач для последующего ожидания.
    """
    try:
        get_worker().stop()
    except Exception as e:
        logger.debug("Остановка воркера: %s", e)
    cancelled_tasks = []
    tasks = getattr(state, "background_tasks", None)
    if isinstance(tasks, dict):
        for task_name, task in list(tasks.items()):
            if task and not task.done():
                task.cancel()
                cancelled_tasks.append(task)
                logger.debug("Отменена фоновая задача: %s", task_name)
        state.background_tasks.clear()
    return cancelled_tasks


async def _await_tasks_cancellation(tasks: list, timeout: float) -> None:
    """Ожидать завершения отменённых задач с таймаутом."""
    if not tasks:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout,
        )
        logger.debug("Фоновые задачи завершены корректно")
    except asyncio.TimeoutError:
        logger.warning(
            "Таймаут (%s сек) ожидания завершения %s фоновых задач",
            timeout,
            len(tasks),
        )


def create_bot() -> commands.Bot:
    """Создать экземпляр бота и обновить state (для первого запуска и переподключения)."""
    bot = commands.Bot(
        command_prefix=Config.COMMAND_PREFIX,
        intents=intents,
        max_messages=Config.BOT_MAX_MESSAGES if Config.BOT_MAX_MESSAGES > 0 else None,
    )
    state.bot = bot

    state.role_cache = RoleCache(bot)
    state.channel_cache = ChannelCache(bot)
    state.start_manager = StartPositionManager(bot)
    state.warehouse_position_manager = WarehousePositionManager(bot)
    state.cleanup_manager = CleanupManager(bot)

    state.view_restorer = ViewRestorer(bot)
    state.apply_grom_manager = ApplyGromPositionManager(bot)
    state.apply_pps_manager = ApplyPpsPositionManager(bot)
    state.apply_osb_manager = ApplyOsbPositionManager(bot)
    state.apply_orls_manager = ApplyOrlsPositionManager(bot)
    state.academy_apply_manager = AcademyApplyPositionManager(bot)
    state.admin_transfer_manager = AdminTransferPositionManager(bot)
    state.firing_position_manager = FiringPositionManager(bot)

    register_events(bot)
    register_admin_commands(bot)
    register_promotion_setup_commands(bot)

    # Сбрасываем фатальную ошибку старта при переподключении
    if hasattr(state, "fatal_startup_error"):
        delattr(state, "fatal_startup_error")

    return bot


# Store-слой и воркер — один раз при загрузке модуля
if not hasattr(state, "background_tasks") or not isinstance(
    getattr(state, "background_tasks", None), dict
):
    state.background_tasks = {}

state.request_store = UserRequestStore(state.active_requests)
state.firing_store = FiringRequestStore(state.active_firing_requests)
state.promotion_store = PromotionRequestStore(state.active_promotion_requests)
state.warehouse_store = WarehouseRequestStore(state.warehouse_requests)

init_worker()

try:
    from services import warehouse_cooldown
    state.warehouse_cooldown = warehouse_cooldown
except Exception as e:
    logger.warning("warehouse_cooldown не загружен: %s", e)

if __name__ == "__main__":
    token = getattr(Config, "TOKEN", None)
    if not token or not str(token).strip():
        logger.critical("Токен бота не задан. Укажите DISCORD_BOT_TOKEN в .env или включите STRICT_ENV=1.")
        sys.exit(1)
    exit_code = 0
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        while True:
            bot = create_bot()
            try:
                loop.run_until_complete(bot.start(Config.TOKEN))
            except discord.LoginFailure:
                logger.critical("Неверный токен в .env")
                exit_code = 1
                break
            except KeyboardInterrupt:
                logger.info("Остановка бота по запросу пользователя")
                break
            except Exception as e:
                logger.error(
                    "Потеря связи с Discord, переподключение через %s сек: %s",
                    RECONNECT_DELAY_SEC,
                    e,
                    exc_info=True,
                )
                _stop_worker_and_tasks()
                time.sleep(RECONNECT_DELAY_SEC)
                continue
            # bot.start() завершился без исключения — соединение закрыто, переподключаемся
            logger.warning(
                "Соединение с Discord закрыто, переподключение через %s сек",
                RECONNECT_DELAY_SEC,
            )
            _stop_worker_and_tasks()
            # Фатальная ошибка старта (БД, GUILD_ID) — не переподключаемся, выходим с кодом 1
            if getattr(state, "fatal_startup_error", None):
                logger.critical(
                    "Фатальная ошибка при старте бота (%s). Завершение без переподключения.",
                    state.fatal_startup_error,
                )
                exit_code = 1
                break
            time.sleep(RECONNECT_DELAY_SEC)
    finally:
        cancelled_tasks = _stop_worker_and_tasks()
        if cancelled_tasks:
            try:
                loop.run_until_complete(
                    _await_tasks_cancellation(cancelled_tasks, SHUTDOWN_TASKS_TIMEOUT_SEC)
                )
            except Exception as e:
                logger.debug("Ожидание завершения задач при выходе: %s", e)
        try:
            from database import close_db
            loop.run_until_complete(close_db())
            logger.info("Соединение с БД закрыто")
        except Exception as e:
            logger.debug("Закрытие БД при выходе: %s", e)
        try:
            import state as _state_for_exit
            fatal_error = getattr(_state_for_exit, "fatal_startup_error", None)
            if fatal_error and exit_code == 0:
                logger.critical(
                    "Фатальная ошибка при старте бота (%s). Процесс будет завершён с кодом 1.",
                    fatal_error,
                )
                exit_code = 1
        except Exception as e:
            logger.debug("Проверка фатальной ошибки старта при выходе: %s", e)
        loop.close()
    sys.exit(exit_code)
