import asyncio
import logging
from typing import Any, Dict

import discord

from config import Config


logger = logging.getLogger(__name__)


_ALERT_QUEUE: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=500)


class DiscordLogAlertHandler(logging.Handler):
    """
    Лог-хендлер, который отправляет CRITICAL (и при желании ERROR) в Discord-канал.

    В emit НИКОГДА не ходим в сеть: только складываем событие в asyncio-очередь
    через call_soon_threadsafe, чтобы не блокировать поток логирования.
    """

    def __init__(self, level: int = logging.CRITICAL):
        super().__init__(level=level)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Если канал для алертов не задан — выходим сразу.
            if not getattr(Config, "LOG_ALERT_CHANNEL_ID", 0):
                return

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if not loop or not loop.is_running():
                return

            msg = self.format(record)
            payload: Dict[str, Any] = {
                "level": record.levelname,
                "logger": record.name,
                "message": msg,
            }

            if record.exc_info:
                try:
                    import traceback

                    exc_text = "".join(traceback.format_exception(*record.exc_info))
                    # Немного ограничим длину трейсбека, чтобы не засорять канал.
                    payload["exc"] = exc_text[:2000]
                except Exception:
                    # Если не смогли сформировать трейсбек — просто продолжаем без него.
                    pass

            def _put() -> None:
                try:
                    if not _ALERT_QUEUE.full():
                        _ALERT_QUEUE.put_nowait(payload)
                except Exception:
                    # Никогда не кидаем исключения наружу из emit.
                    pass

            loop.call_soon_threadsafe(_put)
        except Exception:
            # Любая ошибка в emit игнорируется, чтобы не ломать основной логгер.
            return


def setup_log_alerts() -> None:
    """
    Устанавливает хендлер для отправки CRITICAL/ERROR в Discord-канал.
    Управляется переменными:
      - LOG_ALERT_CHANNEL_ID (ID канала, 0 = отключено)
      - LOG_ALERT_LEVEL (CRITICAL/ERROR/...) — порог для алертов
    """
    channel_id = getattr(Config, "LOG_ALERT_CHANNEL_ID", 0)
    if not channel_id:
        return

    raw_level = getattr(Config, "LOG_ALERT_LEVEL", "CRITICAL")
    if isinstance(raw_level, int):
        level = raw_level
    else:
        name = str(raw_level or "CRITICAL").strip().upper()
        level = getattr(logging, name, logging.CRITICAL)

    handler = DiscordLogAlertHandler(level=level)
    # Формат для алертов берём проще, чем для файловых логов.
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger()
    root.addHandler(handler)
    logger.info(
        "DiscordLogAlertHandler установлен (channel_id=%s, level=%s)",
        channel_id,
        logging.getLevelName(level),
    )


async def alert_dispatch_loop(bot: discord.Client) -> None:
    """
    Фоновая задача, вычитывающая события из очереди и отправляющая их в Discord-канал.
    """
    channel_id = getattr(Config, "LOG_ALERT_CHANNEL_ID", 0)
    if not channel_id:
        logger.info("alert_dispatch_loop: LOG_ALERT_CHANNEL_ID не задан, задача завершится")
        return

    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            payload = await _ALERT_QUEUE.get()
            if not payload:
                continue

            channel = bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                logger.warning(
                    "alert_dispatch_loop: канал алертов %s не найден или имеет неподходящий тип",
                    channel_id,
                )
                continue

            level = payload.get("level", "UNKNOWN")
            logger_name = payload.get("logger", "unknown")
            message = str(payload.get("message", "")).strip()
            exc = str(payload.get("exc", "")).strip()

            # Собираем компактное сообщение для канала алертов.
            content = f"[{level}] `{logger_name}`\n{message}"
            if exc:
                # Трейсбек добавляем в виде блока кода, но немного обрезаем.
                content = f"{content}\n```{exc}```"

            try:
                await channel.send(content=content[:2000])
            except discord.HTTPException as e:
                logger.warning("alert_dispatch_loop: HTTP ошибка при отправке алерта: %s", e, exc_info=True)
            except Exception as e:
                logger.warning("alert_dispatch_loop: неожиданная ошибка при отправке алерта: %s", e, exc_info=True)
        except asyncio.CancelledError:
            logger.info("alert_dispatch_loop остановлен по CancelledError")
            raise
        except Exception as e:
            logger.warning("alert_dispatch_loop: ошибка цикла: %s", e, exc_info=True)
            await asyncio.sleep(5)

