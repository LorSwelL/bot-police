import discord
from config import Config
from views.apply_channel_view import ApplyChannelView
from .base_position import BasePositionManager


TITLE = "ПЕРЕВОД В ОСБ"

DESCRIPTION = (
    "**Критерии для перевода:**\n\n"
    "> Звание: от сержанта полиции\n\n"
    "> Знание ФЗ «О ПОЛИЦИИ»\n"
    "> Знание ФЗ «ОБ ОРУЖИИ»\n"
    "> Знание ФЗ «О ДОКУМЕНТООБОРОТЕ»\n"
    "> Знание ФЗ «О ГОСУДАРСТВЕННОЙ СЛУЖБЕ»\n"
    "> Знание ФЗ «О ГОСУДАРСТВЕННОЙ ТАЙНЕ»\n"
    "> Знание ФКЗ УПК\n"
    "> Знание ФКЗ ПК\n"
    "> Знание КоАПРФ\n"
    "> Знание УКРФ\n"
    "> Знание Внутреннего Устава\n\n"
    "**ПОДАТЬ ЗАЯВКУ ИЗ:**"
)


class ApplyOsbPositionManager(BasePositionManager):
    @property
    def channel_id(self) -> int:
        return Config.CHANNEL_APPLY_OSB

    @property
    def check_interval(self) -> int:
        return 180

    async def get_embed(self) -> discord.Embed:
        embed = discord.Embed(title=TITLE, description=DESCRIPTION, color=discord.Color.red())
        return embed

    async def get_view(self) -> discord.ui.View:
        return ApplyChannelView("osb", [("pps", "「ППС」"), ("orls", "「ОРЛС」"), ("grom", "「ГРОМ」")])

    async def should_keep_message(self, message: discord.Message) -> bool:
        return bool(message.embeds and message.embeds[0].title == TITLE)
