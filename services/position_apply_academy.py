import discord
from config import Config
from views.academy_apply_view import AcademyApplyView
from views.academy_promotion_apply_view import AcademyPromotionApplyView
from .base_position import BasePositionManager

import logging
logger = logging.getLogger(__name__)


APPLY_TITLE = "ЗАЯВКА ИЗ АКАДЕМИИ"
APPLY_DESCRIPTION = (
    "**Выпускники академии:** выберите отдел для перевода.\n\n"
    "Нажмите кнопку нужного отдела и заполните заявку."
)

PROMO_TITLE = "РАПОРТЫ НА ПОВЫШЕНИЕ АКАДЕМИИ"
PROMO_DESCRIPTION = (
    "**Рапорты на повышение:** выберите нужное повышение и заполните рапорт.\n\n"
    "После одобрения рапорта звание и роли будут обновлены автоматически."
)


class AcademyPositionManager(BasePositionManager):
    def __init__(self, bot):
        super().__init__(bot)
        self.apply_message_id: int | None = None
        self.promotion_message_id: int | None = None

    @property
    def channel_id(self) -> int:
        return Config.ACADEMY_CHANNEL_ID

    @property
    def check_interval(self) -> int:
        return 120

    async def get_embed(self) -> discord.Embed:
        # Не используется в переопределённом ensure_position
        return discord.Embed(title=APPLY_TITLE, description=APPLY_DESCRIPTION, color=discord.Color.gold())

    async def get_view(self) -> discord.ui.View:
        # Не используется в переопределённом ensure_position
        return AcademyApplyView()

    async def should_keep_message(self, message: discord.Message) -> bool:
        # Не используется в переопределённом ensure_position
        return False

    async def _build_apply_message(self, channel: discord.TextChannel) -> discord.Message:
        embed = discord.Embed(
            title=APPLY_TITLE,
            description=APPLY_DESCRIPTION,
            color=discord.Color.gold(),
        )
        view = AcademyApplyView()
        msg = await channel.send(embed=embed, view=view)
        self.apply_message_id = msg.id
        return msg

    async def _build_promotion_message(self, channel: discord.TextChannel) -> discord.Message:
        embed = discord.Embed(
            title=PROMO_TITLE,
            description=PROMO_DESCRIPTION,
            color=discord.Color.blue(),
        )
        view = AcademyPromotionApplyView()
        msg = await channel.send(embed=embed, view=view)
        self.promotion_message_id = msg.id
        return msg

    async def ensure_position(self):
        if self.is_updating:
            return

        channel = None
        try:
            import state as _state_for_channel  # локальный импорт, чтобы избежать циклов
            cache = getattr(_state_for_channel, "channel_cache", None)
            if cache is not None:
                channel = await cache.get_channel(self.channel_id)
        except Exception:
            logger.debug("AcademyPositionManager ensure_position: не удалось получить канал через cache", exc_info=True)
            channel = None
        if channel is None:
            channel = self.bot.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            self.is_updating = True

            last_messages: list[discord.Message] = []
            async for msg in channel.history(limit=5):
                last_messages.append(msg)
            # last_messages[0] - самый новый
            if len(last_messages) >= 2:
                newest = last_messages[0]
                second = last_messages[1]
                if (
                    newest.author == self.bot.user
                    and second.author == self.bot.user
                    and newest.embeds
                    and second.embeds
                    and (newest.embeds[0].title or "").strip() == PROMO_TITLE
                    and (second.embeds[0].title or "").strip() == APPLY_TITLE
                ):
                    self.promotion_message_id = newest.id
                    self.apply_message_id = second.id
                    return

            # Иначе пересоздаём пару системных сообщений
            async for msg in channel.history(limit=50):
                try:
                    if (
                        msg.author == self.bot.user
                        and msg.embeds
                        and (msg.embeds[0].title or "").strip()
                        in {APPLY_TITLE, PROMO_TITLE}
                    ):
                        await msg.delete()
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    return
                except discord.HTTPException:
                    continue

            apply_msg = await self._build_apply_message(channel)
            promo_msg = await self._build_promotion_message(channel)
            self.apply_message_id = apply_msg.id
            self.promotion_message_id = promo_msg.id
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                "Ошибка AcademyPositionManager.ensure_position: %s",
                e,
                exc_info=True,
            )
        finally:
            self.is_updating = False


# Обратная совместимость с main.py / state.academy_apply_manager
AcademyApplyPositionManager = AcademyPositionManager
