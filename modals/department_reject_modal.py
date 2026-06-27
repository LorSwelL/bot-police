from __future__ import annotations

import asyncio
import logging

import discord
from discord.ui import Modal, TextInput

from config import Config
from views.theme import RED
from database import delete_department_transfer_request
from state import active_department_transfers
from utils.embed_utils import copy_embed, update_embed_status
from utils.interaction_helpers import safe_followup_or_response

logger = logging.getLogger(__name__)


class DepartmentRejectModal(Modal, title="Отклонение заявки"):
    def __init__(self, message_id: int, user_id: int, target_dept: str):
        super().__init__()
        self.message_id = int(message_id)
        self.user_id = int(user_id)
        self.target_dept = (target_dept or "").strip().lower()
        self.reason = TextInput(
            label="Причина отклонения",
            placeholder="Укажите причину отказа",
            max_length=Config.MAX_REASON_LENGTH,
            style=discord.TextStyle.paragraph,
            required=True,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            guild = interaction.guild
            if not guild:
                await interaction.followup.send("❌ Только на сервере.", ephemeral=True)
                return

            if not getattr(interaction.channel, "id", None):
                await interaction.followup.send("❌ Канал недоступен.", ephemeral=True)
                return

            try:
                msg = await interaction.channel.fetch_message(self.message_id)
            except discord.NotFound:
                await interaction.followup.send("❌ Сообщение заявки не найдено.", ephemeral=True)
                return
            except discord.Forbidden:
                await interaction.followup.send("❌ Нет доступа к сообщению заявки.", ephemeral=True)
                return
            except discord.HTTPException as e:
                logger.warning("DepartmentReject: HTTP ошибка fetch_message %s: %s", self.message_id, e)
                await interaction.followup.send("❌ Ошибка Discord API при получении сообщения.", ephemeral=True)
                return

            if not msg.embeds:
                await interaction.followup.send("❌ У сообщения нет embed.", ephemeral=True)
                return

            reason_text = (self.reason.value or "").strip() or "Не указана"
            embed = copy_embed(msg.embeds[0])
            embed = update_embed_status(embed, "❌ Отклонено", RED)
            embed.add_field(name="Причина отказа", value=reason_text[:1024], inline=False)
            embed.add_field(name="Отклонил", value=interaction.user.mention, inline=False)

            try:
                await msg.edit(embed=embed, view=None)
            except discord.NotFound:
                await interaction.followup.send("❌ Сообщение заявки было удалено.", ephemeral=True)
                return
            except discord.Forbidden:
                await interaction.followup.send("❌ У бота нет прав на редактирование сообщения.", ephemeral=True)
                return
            except discord.HTTPException as e:
                logger.warning("DepartmentReject: HTTP ошибка edit %s: %s", self.message_id, e)
                await interaction.followup.send("❌ Ошибка Discord API при обновлении заявки.", ephemeral=True)
                return

            member = guild.get_member(self.user_id)
            if not member:
                try:
                    member = await guild.fetch_member(self.user_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    member = None
            if member:
                try:
                    await member.send(
                        f"❌ Ваша заявка на перевод была отклонена.\n**Причина:** {reason_text}"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

            active_department_transfers.pop(self.message_id, None)
            await delete_department_transfer_request(self.message_id)

            await interaction.followup.send("✅ Заявка отклонена, пользователь уведомлён.", ephemeral=True)
        except Exception as e:
            logger.error("Ошибка отклонения заявки: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, "❌ Ошибка при отклонении.", ephemeral=True)
