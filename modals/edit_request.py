import discord
from discord.ui import Modal, TextInput
import logging
from datetime import datetime
import asyncio

from config import Config
from views.message_texts import ErrorMessages, SuccessMessages
from enums import RequestType
from utils.validators import Validators
from utils.interaction_helpers import safe_followup_or_response
from constants import FieldNames
from database import save_request

logger = logging.getLogger(__name__)


class EditRequestModal(Modal):
    def __init__(self, user_id: int, request_type: RequestType, current_data: dict, message_id: int):
        title = f"Редактирование заявки — {request_type.get_title()}"
        super().__init__(title=title)
        self.user_id = user_id
        self.request_type = request_type
        self.message_id = message_id
        self.current_data = current_data or {}

        self.name = TextInput(
            label="Имя",
            default=self.current_data.get("name", ""),
            max_length=Config.MAX_NAME_LENGTH,
            min_length=Config.MIN_NAME_LENGTH,
            required=True,
        )
        self.surname = TextInput(
            label="Фамилия",
            default=self.current_data.get("surname", ""),
            max_length=Config.MAX_NAME_LENGTH,
            min_length=Config.MIN_NAME_LENGTH,
            required=True,
        )
        self.static_id = TextInput(
            label="Статик ID",
            placeholder="Введите 6 цифр",
            default=str(self.current_data.get("static_id", "")).replace("-", ""),
            max_length=10,
            min_length=Config.STATIC_ID_LENGTH,
            required=True,
        )
        self.add_item(self.name)
        self.add_item(self.surname)
        self.add_item(self.static_id)

        if request_type == RequestType.CADET:
            self.reason = TextInput(
                label="Причина",
                default=self.current_data.get("reason", ""),
                max_length=Config.MAX_REASON_LENGTH,
                style=discord.TextStyle.paragraph,
                required=True,
            )
            self.add_item(self.reason)
        elif request_type == RequestType.TRANSFER:
            self.rank = TextInput(
                label="Звание",
                default=self.current_data.get("rank", ""),
                max_length=Config.MAX_RANK_LENGTH,
                required=True,
            )
            self.approval = TextInput(
                label="Одобрение",
                default=self.current_data.get("approval", ""),
                max_length=Config.MAX_REASON_LENGTH,
                style=discord.TextStyle.paragraph,
                required=True,
            )
            self.add_item(self.rank)
            self.add_item(self.approval)
        elif request_type == RequestType.GOV:
            self.approval = TextInput(
                label="Одобрение",
                default=self.current_data.get("approval", ""),
                max_length=Config.MAX_REASON_LENGTH,
                style=discord.TextStyle.paragraph,
                required=True,
            )
            self.add_item(self.approval)

    async def validate_all(self):
        try:
            validated = {}

            valid, name = Validators.validate_name(self.name.value)
            if not valid:
                return False, {"error": f"ошибка в имени: {name}"}
            validated["name"] = name

            valid, surname = Validators.validate_name(self.surname.value)
            if not valid:
                return False, {"error": f"ошибка в фамилии: {surname}"}
            validated["surname"] = surname

            valid, static = Validators.format_static_id(self.static_id.value)
            if not valid:
                return False, {"error": f"ошибка в static id: {static}"}
            validated["static_id"] = static

            if self.request_type == RequestType.CADET:
                valid, reason = Validators.validate_reason(self.reason.value)
                if not valid:
                    return False, {"error": f"ошибка: {reason}"}
                validated["reason"] = reason
            elif self.request_type == RequestType.TRANSFER:
                valid, rank = Validators.validate_rank(self.rank.value)
                if not valid:
                    return False, {"error": f"ошибка в звании: {rank}"}
                validated["rank"] = rank

                valid, approval = Validators.validate_reason(self.approval.value, require_link=True)
                if not valid:
                    return False, {"error": f"ошибка: {approval}"}
                validated["approval"] = approval
            elif self.request_type == RequestType.GOV:
                valid, approval = Validators.validate_reason(self.approval.value, require_link=True)
                if not valid:
                    return False, {"error": f"ошибка: {approval}"}
                validated["approval"] = approval

            return True, validated
        except Exception as e:
            logger.error("Ошибка валидации: %s", e, exc_info=True)
            return False, {"error": "произошла ошибка при проверке данных"}

    async def create_updated_embed(self, validated_data, original_embed: discord.Embed):
        new_embed = discord.Embed(
            title=original_embed.title,
            color=original_embed.color,
            timestamp=datetime.now(),
        )

        new_embed.add_field(name=FieldNames.NAME, value=validated_data["name"], inline=True)
        new_embed.add_field(name=FieldNames.SURNAME, value=validated_data["surname"], inline=True)
        new_embed.add_field(name=FieldNames.STATIC_ID, value=validated_data["static_id"], inline=True)

        if self.request_type == RequestType.CADET:
            new_embed.add_field(name=FieldNames.REASON, value=validated_data["reason"], inline=False)
        elif self.request_type == RequestType.TRANSFER:
            new_embed.add_field(name=FieldNames.RANK, value=validated_data["rank"], inline=True)
            new_embed.add_field(name=FieldNames.APPROVAL, value=validated_data["approval"], inline=False)
        elif self.request_type == RequestType.GOV:
            new_embed.add_field(name=FieldNames.APPROVAL, value=validated_data["approval"], inline=False)

        replaced = {
            FieldNames.NAME,
            FieldNames.SURNAME,
            FieldNames.STATIC_ID,
            FieldNames.REASON,
            FieldNames.RANK,
            FieldNames.APPROVAL,
        }

        for field in original_embed.fields:
            if field.name not in replaced:
                new_embed.add_field(name=field.name, value=field.value, inline=field.inline)

        if original_embed.footer:
            new_embed.set_footer(text=original_embed.footer.text, icon_url=original_embed.footer.icon_url)

        return new_embed

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ это не ваша заявка!", ephemeral=True)
                return

            success, result = await self.validate_all()
            if not success:
                await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            if not getattr(interaction.channel, "id", None):
                await interaction.followup.send("❌ Канал недоступен.", ephemeral=True)
                return

            try:
                message = await interaction.channel.fetch_message(self.message_id)
            except discord.NotFound:
                await interaction.followup.send(
                    ErrorMessages.NOT_FOUND.format(item="сообщение"),
                    ephemeral=True,
                )
                return
            except discord.Forbidden:
                await interaction.followup.send("❌ У бота нет доступа к сообщению.", ephemeral=True)
                return
            except discord.HTTPException as e:
                logger.warning("EditRequest: HTTP ошибка fetch_message %s: %s", self.message_id, e)
                await interaction.followup.send("❌ Ошибка Discord API при получении сообщения.", ephemeral=True)
                return

            if not message or not message.embeds:
                await interaction.followup.send(
                    "❌ Невозможно отредактировать заявку: у сообщения нет embed.",
                    ephemeral=True,
                )
                return

            new_embed = await self.create_updated_embed(result, message.embeds[0])

            try:
                import state as _state_for_store

                store = getattr(_state_for_store, "request_store", None)
            except Exception:
                logger.debug("EditRequestModal: не удалось получить request_store", exc_info=True)
                store = None

            if store is not None:
                existing = store.get_by_message_id(self.message_id) or {}
            else:
                from state import active_requests  # локальный импорт

                existing = (active_requests.get(self.message_id, {}) or {}).copy()
                if not existing:
                    existing = dict(self.current_data)

            if not existing:
                existing = dict(self.current_data)

            existing.update(result)
            existing["embed"] = new_embed.to_dict()
            existing["message_id"] = self.message_id
            existing.setdefault("user_id", self.user_id)
            existing.setdefault("request_type", self.request_type.value)
            existing.setdefault(
                "created_at",
                self.current_data.get("created_at", datetime.now().isoformat()),
            )

            if message.jump_url:
                existing["message_link"] = message.jump_url

            if store is not None:
                await store.upsert_active(self.message_id, existing)
            else:
                from state import active_requests  # локальный импорт

                active_requests[self.message_id] = existing
                await save_request("requests", self.message_id, existing)

            try:
                await message.edit(embed=new_embed)
            except discord.NotFound:
                await interaction.followup.send("❌ Сообщение заявки было удалено.", ephemeral=True)
                return
            except discord.Forbidden:
                await interaction.followup.send("❌ У бота нет прав на редактирование сообщения.", ephemeral=True)
                return
            except discord.HTTPException as e:
                logger.warning("EditRequest: HTTP ошибка edit %s: %s", self.message_id, e)
                await interaction.followup.send("❌ Ошибка Discord API при обновлении заявки.", ephemeral=True)
                return

            await interaction.followup.send(SuccessMessages.EDITED, ephemeral=True)
            logger.info("Заявка %s отредактирована пользователем %s", self.message_id, interaction.user.id)

        except Exception as e:
            logger.error("Ошибка при редактировании заявки: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, ErrorMessages.GENERIC, ephemeral=True)