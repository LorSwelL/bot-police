import discord
from discord.ui import Modal, TextInput
import logging
import asyncio

from config import Config
from views.theme import RED
from views.message_texts import ErrorMessages
from enums import RequestType
from utils.validators import Validators
from utils.interaction_helpers import safe_followup_or_response
from utils.embed_utils import copy_embed, add_officer_field, add_reject_reason
from database import delete_request
from constants import StatusValues
from services.action_locks import action_lock

logger = logging.getLogger(__name__)

class RejectReasonModal(Modal, title='Отклонение заявки'):
    def __init__(self, user_id: int, request_type: RequestType, message_id: int):
        super().__init__()
        self.user_id = user_id
        self.request_type = request_type
        self.message_id = message_id
        self.reason = TextInput(
            label='Причина отказа',
            placeholder='Укажите причину отклонения заявки',
            max_length=Config.MAX_REASON_LENGTH,
            style=discord.TextStyle.paragraph,
            required=True
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            async with action_lock(self.message_id, "отклонение заявки"):
                if not interaction.guild:
                    await interaction.response.send_message("❌ Команда доступна только на сервере.", ephemeral=True)
                    return
                staff_role = interaction.guild.get_role(self.request_type.get_staff_role_id())
                if staff_role not in interaction.user.roles:
                    await interaction.response.send_message(ErrorMessages.NO_PERMISSION, ephemeral=True)
                    return

                valid, reason = Validators.validate_reason(self.reason.value)
                if not valid:
                    await interaction.response.send_message(f"❌ {reason}", ephemeral=True)
                    return

                try:
                    import state as _state_for_store

                    store = getattr(_state_for_store, "request_store", None)
                except Exception:
                    logger.debug("RejectReasonModal: не удалось получить request_store", exc_info=True)
                    store = None

                if store is not None:
                    request_data = store.get_by_message_id(self.message_id)
                else:
                    from state import active_requests  # локальный импорт

                    request_data = active_requests.get(self.message_id)
                if not request_data:
                    await interaction.response.send_message(
                        ErrorMessages.NOT_FOUND.format(item="заявка"),
                        ephemeral=True,
                    )
                    return

                await interaction.response.defer(ephemeral=True)

                if not getattr(interaction.channel, "id", None):
                    await interaction.followup.send("❌ Канал недоступен.", ephemeral=True)
                    return

                member = interaction.guild.get_member(self.user_id) if interaction.guild else None
                try:
                    message = await interaction.channel.fetch_message(self.message_id)
                except discord.NotFound:
                    await interaction.followup.send(
                        ErrorMessages.NOT_FOUND.format(item="сообщение заявки"),
                        ephemeral=True,
                    )
                    return
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ У бота нет доступа к сообщению заявки.",
                        ephemeral=True,
                    )
                    return
                except discord.HTTPException as e:
                    logger.warning("RejectReason: HTTP ошибка fetch_message %s: %s", self.message_id, e)
                    await interaction.followup.send("❌ Ошибка Discord API при получении сообщения.", ephemeral=True)
                    return

                if not message.embeds:
                    await interaction.followup.send("❌ У сообщения заявки отсутствует embed.", ephemeral=True)
                    return

                embed = copy_embed(message.embeds[0])
                embed = add_officer_field(embed, interaction.user.mention)
                embed = add_reject_reason(embed, reason)
                embed.color = RED

                try:
                    await message.edit(embed=embed, view=None)
                except discord.NotFound:
                    await interaction.followup.send("❌ Сообщение заявки было удалено.", ephemeral=True)
                    return
                except discord.Forbidden:
                    await interaction.followup.send(
                        "❌ У бота нет прав на редактирование сообщения.",
                        ephemeral=True,
                    )
                    return
                except discord.HTTPException as e:
                    logger.warning("RejectReason: HTTP ошибка edit %s: %s", self.message_id, e)
                    await interaction.followup.send("❌ Ошибка Discord API при обновлении заявки.", ephemeral=True)
                    return

                dm_warning = None
                if member:
                    try:
                        notification = discord.Embed(
                            title="Заявка отклонена",
                            color=RED,
                            description=f"**{interaction.guild.name}**\n\nВаша заявка была отклонена.",
                            timestamp=interaction.created_at,
                        )
                        notification.add_field(name="Причина", value=reason, inline=False)
                        notification.add_field(name="Отклонил", value=interaction.user.mention, inline=True)
                        await member.send(embed=notification)
                    except discord.Forbidden:
                        dm_warning = f"⚠️ не удалось отправить уведомление пользователю {member.mention}"

                if store is not None:
                    await store.remove_active(self.message_id)
                else:
                    from state import active_requests  # локальный импорт

                    try:
                        await delete_request("requests", self.message_id)
                    except Exception as e:
                        logger.warning(
                            "RejectReason: не удалось удалить заявку из БД message_id=%s: %s",
                            self.message_id,
                            e,
                            exc_info=True,
                        )
                    else:
                        active_requests.pop(self.message_id, None)

                await interaction.followup.send(f"✅ Заявка отклонена. Причина: {reason}", ephemeral=True)
                if dm_warning:
                    await interaction.followup.send(dm_warning, ephemeral=True)
                logger.info("Заявка %s отклонена сотрудником %s", self.message_id, interaction.user.id)

        except RuntimeError as e:
            if str(e) == "ACTION_ALREADY_IN_PROGRESS":
                await safe_followup_or_response(
                    interaction,
                    "⚠️ Это действие уже выполняется другим нажатием.",
                    ephemeral=True,
                )
                return

            logger.error("Ошибка блокировки при отклонении заявки %s: %s", self.message_id, e, exc_info=True)
            await safe_followup_or_response(interaction, ErrorMessages.GENERIC, ephemeral=True)

        except Exception as e:
            logger.error("Ошибка при отклонении заявки: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, ErrorMessages.GENERIC, ephemeral=True)