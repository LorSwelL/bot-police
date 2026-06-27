import discord
from config import Config
from views.warehouse_start import WarehouseStartView
from .base_position import BasePositionManager

class WarehousePositionManager(BasePositionManager):

    @property
    def channel_id(self) -> int:
        return Config.WAREHOUSE_REQUEST_CHANNEL_ID

    @property
    def check_interval(self) -> int:
        return 30

    async def get_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=Config.WAREHOUSE_START_TITLE,
            description=Config.WAREHOUSE_START_DESCRIPTION.format(
                cooldown_hours=Config.WAREHOUSE_COOLDOWN_HOURS
            ),
            color=discord.Color.blue()
        )
        return embed

    async def get_view(self) -> discord.ui.View:
        return WarehouseStartView()

    async def should_keep_message(self, message: discord.Message) -> bool:
        return (message.embeds and
                message.embeds[0].title == Config.WAREHOUSE_START_TITLE)