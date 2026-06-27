import discord
from config import Config
from views.apply_channel_view import ApplyChannelView
from .base_position import BasePositionManager


TITLE = "ПЕРЕВОД В ОРЛС"
DESCRIPTION = (
    "**Критерии для перевода:**\n\n"
    "> Умение работать с людьми\n"
    "> Умение аргументированно доносить информацию\n"
    "> Ответственность и целеустремлённость\n"
    "> Базовые знания работы увд\n"
    "> Звание: от сержанта полиции\n\n"
    "**ПОДАТЬ ЗАЯВКУ ИЗ:**"
)


class ApplyOrlsPositionManager(BasePositionManager):
    @property
    def channel_id(self) -> int:
        return Config.CHANNEL_APPLY_ORLS

    @property
    def check_interval(self) -> int:
        return 180

    async def get_embed(self) -> discord.Embed:
        embed = discord.Embed(title=TITLE, description=DESCRIPTION, color=discord.Color.gold())
        return embed

    async def get_view(self) -> discord.ui.View:
        return ApplyChannelView("orls", [("pps", "「ППС」"), ("grom", "「ГРОМ」"), ("osb", "「ОСБ」")])

    async def should_keep_message(self, message: discord.Message) -> bool:
        return bool(message.embeds and message.embeds[0].title == TITLE)
