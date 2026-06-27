import discord
from config import Config
from views.apply_channel_view import ApplyChannelView
from .base_position import BasePositionManager


TITLE = "ПЕРЕВОД В ППС"
DESCRIPTION = (
    "**Критерии для перевода:**\n\n"
    "> Звание: сержант полиции\n"
    "> Знание УКРФ\n"
    "> Знание КоАП\n\n"
    "**ПОДАТЬ ЗАЯВКУ ИЗ:**"
)


class ApplyPpsPositionManager(BasePositionManager):
    @property
    def channel_id(self) -> int:
        return Config.CHANNEL_APPLY_PPS

    @property
    def check_interval(self) -> int:
        return 180

    async def get_embed(self) -> discord.Embed:
        embed = discord.Embed(title=TITLE, description=DESCRIPTION, color=discord.Color.green())
        return embed

    async def get_view(self) -> discord.ui.View:
        return ApplyChannelView("pps", [("grom", "「ГРОМ」"), ("orls", "「ОРЛС」"), ("osb", "「ОСБ」")])

    async def should_keep_message(self, message: discord.Message) -> bool:
        return bool(message.embeds and message.embeds[0].title == TITLE)
