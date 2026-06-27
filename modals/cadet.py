import discord
from .base import BaseRequestModal
from .mixins import ReasonMixin
from enums import RequestType
from constants import FieldNames, StatusValues

class CadetModal(BaseRequestModal, ReasonMixin):
    def __init__(self, member=None):
        super().__init__("заявка на получение роли", RequestType.CADET, member=member)
        self.add_reason_field()

    async def validate_specific(self, common):
        return await self.validate_reason(common)

    async def create_embed(self, data, interaction):
        embed = discord.Embed(
            title=self.request_type.get_title(),
            color=self.request_type.get_color(),
            timestamp=interaction.created_at
        )
        embed.add_field(name=FieldNames.NAME, value=data['name'], inline=True)
        embed.add_field(name=FieldNames.SURNAME, value=data['surname'], inline=True)
        embed.add_field(name=FieldNames.STATIC_ID, value=data['static_id'], inline=True)
        embed.add_field(name=FieldNames.REASON, value=data['reason'], inline=False)
        embed.add_field(name=FieldNames.STATUS, value=StatusValues.PENDING, inline=True)
        embed.set_footer(text=interaction.user.display_name if interaction.user else "Пользователь", icon_url=(getattr(interaction.user, "display_avatar", None) and getattr(interaction.user.display_avatar, "url", None)) if interaction.user else None)
        return embed