import logging
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import discord

from config import Config

logger = logging.getLogger(__name__)


class BasePositionManager(ABC):
    def __init__(self, bot):
        self.bot = bot
        self.message_id = None
        self.is_updating = False
        self.last_ok_at: datetime | None = None

    @property
    @abstractmethod
    def channel_id(self) -> int:
        pass

    @property
    def check_interval(self) -> int:
        return Config.BASE_POSITION_CHECK_INTERVAL

    @abstractmethod
    async def get_embed(self) -> discord.Embed:
        pass

    @abstractmethod
    async def get_view(self) -> discord.ui.View:
        pass

    @abstractmethod
    async def should_keep_message(self, message: discord.Message) -> bool:
        pass

    async def find_our_message(self, channel: discord.TextChannel):
        try:
            async for msg in channel.history(limit=Config.BASE_POSITION_HISTORY_LIMIT):
                try:
                    if msg.author == self.bot.user and await self.should_keep_message(msg):
                        return msg
                except Exception as e:
                    logger.warning(
                        "⚠️ Ошибка проверки сообщения %s в канале %s: %s",
                        getattr(msg, "id", "unknown"),
                        self.channel_id,
                        e,
                        exc_info=True,
                    )
        except discord.Forbidden:
            logger.warning("⚠️ Нет прав на чтение истории канала %s", self.channel_id)
        except discord.HTTPException as e:
            logger.warning("⚠️ HTTP ошибка при чтении истории канала %s: %s", self.channel_id, e)
        return None

    async def ensure_position(self):
        if self.is_updating:
            logger.debug("Пропуск ensure_position: обновление уже выполняется (канал %s)", self.channel_id)
            return


        channel = None
        try:
            import state as _state_for_channel  # локальный импорт, чтобы избежать циклов
            cache = getattr(_state_for_channel, "channel_cache", None)
            if cache is not None:
                channel = await cache.get_channel(self.channel_id)
        except Exception:
            logger.debug("BasePositionManager ensure_position: не удалось получить канал через cache (channel_id=%s)", self.channel_id, exc_info=True)
            channel = None
        if channel is None:
            channel = self.bot.get_channel(self.channel_id)
        if not channel:
            logger.error("Канал %s не найден", self.channel_id)
            return

        try:
            self.is_updating = True


            current_message = None
            if self.message_id:
                try:
                    current_message = await channel.fetch_message(int(self.message_id))

                    if not await self.should_keep_message(current_message):
                        logger.info(
                            "Сообщение %s в канале %s больше не подходит под критерий, ищем заново",
                            self.message_id,
                            self.channel_id,
                        )
                        current_message = None
                        self.message_id = None

                except discord.NotFound:
                    logger.info("Сообщение %s не найдено в канале %s", self.message_id, self.channel_id)
                    self.message_id = None
                except discord.Forbidden:
                    logger.warning("Нет прав на fetch_message в канале %s", self.channel_id)
                    return
                except discord.HTTPException as e:
                    logger.warning("HTTP ошибка fetch_message (%s) в канале %s: %s", self.message_id, self.channel_id, e)
                    return
                except Exception as e:
                    logger.error(
                        "Ошибка при получении сообщения %s в канале %s: %s",
                        self.message_id,
                        self.channel_id,
                        e,
                        exc_info=True,
                    )
                    self.message_id = None


            if not current_message:
                current_message = await self.find_our_message(channel)
                if current_message:
                    self.message_id = current_message.id


            last_message = None
            try:
                async for msg in channel.history(limit=1):
                    last_message = msg
                    break
            except discord.Forbidden:
                logger.warning("⚠️ Нет прав на чтение последнего сообщения в канале %s", self.channel_id)
                return
            except discord.HTTPException as e:
                logger.warning("⚠️ HTTP ошибка при получении последнего сообщения в канале %s: %s", self.channel_id, e)
                return


            need_update = False

            if not current_message:
                need_update = True
                logger.info("Сообщение не найдено в канале %s - создаем", self.channel_id)
            elif last_message and current_message.id != last_message.id:
                need_update = True
                logger.info("Сообщение не внизу канала %s - перемещаем", self.channel_id)
            elif len(current_message.components) == 0:
                need_update = True
                logger.info("Кнопки пропали в канале %s - восстанавливаем", self.channel_id)

            if need_update:

                if current_message:
                    try:
                        await current_message.delete()
                    except discord.NotFound:
                        logger.info("Старое сообщение уже удалено (канал %s)", self.channel_id)
                    except discord.Forbidden:
                        logger.warning("Нет прав на удаление старого сообщения в канале %s", self.channel_id)
                        return
                    except discord.HTTPException as e:
                        logger.warning("HTTP ошибка при удалении старого сообщения в канале %s: %s", self.channel_id, e)
                        return


                embed = await self.get_embed()
                view = await self.get_view()

                try:
                    new_message = await channel.send(embed=embed, view=view)
                except discord.Forbidden:
                    logger.warning("Нет прав на отправку сообщения в канале %s", self.channel_id)
                    return
                except discord.HTTPException as e:
                    logger.warning("HTTP ошибка при отправке сообщения в канале %s: %s", self.channel_id, e)
                    return

                self.message_id = new_message.id


                await self._remove_duplicates(channel)

                logger.info("🔄 Сообщение обновлено в канале %s (msg_id=%s)", self.channel_id, self.message_id)

            # успешный проход ensure_position (даже без обновления) — сохраняем отметку
            self.last_ok_at = datetime.now(timezone.utc)

        except Exception as e:
            logger.error("Ошибка в ensure_position для канала %s: %s", self.channel_id, e, exc_info=True)
        finally:
            self.is_updating = False

    async def _remove_duplicates(self, channel: discord.TextChannel):
        try:
            async for msg in channel.history(limit=Config.BASE_POSITION_HISTORY_LIMIT):
                try:
                    if (
                        msg.author == self.bot.user
                        and msg.id != self.message_id
                        and await self.should_keep_message(msg)
                    ):
                        await msg.delete()
                        logger.info("🧹 Удалён дубликат сообщения %s в канале %s", msg.id, self.channel_id)
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    logger.warning("⚠️ Нет прав на удаление дубликатов в канале %s", self.channel_id)
                    return
                except discord.HTTPException as e:
                    logger.warning("⚠️ HTTP ошибка при удалении дубликата в канале %s: %s", self.channel_id, e)
                except Exception as e:
                    logger.warning("⚠️ Ошибка обработки дубликата в канале %s: %s", self.channel_id, e, exc_info=True)
        except discord.Forbidden:
            logger.warning("⚠️ Нет прав на чтение истории для удаления дубликатов (канал %s)", self.channel_id)
        except discord.HTTPException as e:
            logger.warning("⚠️ HTTP ошибка при чтении истории для удаления дубликатов (канал %s): %s", self.channel_id, e)
        except Exception as e:
            logger.error("Ошибка при удалении дубликатов в канале %s: %s", self.channel_id, e, exc_info=True)

    async def start_checking(self):
        await self.bot.wait_until_ready()


        await self.ensure_position()


        while not self.bot.is_closed():
            try:
                await asyncio.sleep(self.check_interval)
                await self.ensure_position()
            except asyncio.CancelledError:
                logger.info("Фоновая проверка позиции остановлена (канал %s)", self.channel_id)
                raise
            except Exception as e:
                logger.error("Ошибка в цикле start_checking (канал %s): %s", self.channel_id, e, exc_info=True)
                await asyncio.sleep(5)