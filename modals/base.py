import discord
from discord.ui import Modal, TextInput
import logging
from typing import Dict, Any, Tuple
from datetime import datetime
from config import Config
from views.message_texts import ErrorMessages, SuccessMessages
from utils.validators import Validators
from utils.interaction_helpers import safe_followup_or_response
import state
from enums import RequestType
import asyncio

logger = logging.getLogger(__name__)


class BaseRequestModal(Modal):
    def __init__(self, title: str, request_type: RequestType, member=None):
        super().__init__(title=title)
        self.request_type = request_type
        min_len = getattr(Config, "MIN_NAME_LENGTH", 2)

        self.name = TextInput(
            label="Имя",
            placeholder="Введите ваше имя",
            max_length=Config.MAX_NAME_LENGTH,
            min_length=min_len,
            required=True,
        )
        self.surname = TextInput(
            label="Фамилия",
            placeholder="Введите вашу фамилию",
            max_length=Config.MAX_NAME_LENGTH,
            min_length=min_len,
            required=True,
        )
        self.static_id = TextInput(
            label="Статик ID",
            placeholder="Введите 6 цифр (пример: 537123)",
            max_length=10,
            min_length=Config.STATIC_ID_LENGTH,
            required=True,
        )
        self.add_item(self.name)
        self.add_item(self.surname)
        self.add_item(self.static_id)

    async def validate_common(self) -> Tuple[bool, Dict[str, Any]]:
        try:
            validated = {}
            for field, validator, key in [
                (self.name, Validators.validate_name, 'name'),
                (self.surname, Validators.validate_name, 'surname')
            ]:
                valid, result = validator(field.value)
                if not valid:
                    return False, {"error": f"ошибка в {key}: {result}"}
                validated[key] = result
            valid, static = Validators.format_static_id(self.static_id.value)
            if not valid:
                return False, {"error": f"ошибка в static id: {static}"}
            validated['static_id'] = static
            return True, validated
        except Exception as e:
            logger.error("ошибка валидации: %s", e, exc_info=True)
            return False, {"error": "произошла ошибка при проверке данных"}

    async def validate_specific(self, common: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        return True, common

    async def validate_all(self) -> Tuple[bool, Dict[str, Any]]:
        success, common = await self.validate_common()
        if not success:
            return success, common
        return await self.validate_specific(common)

    async def create_embed(self, validated_data: Dict[str, Any], interaction: discord.Interaction) -> discord.Embed:
        raise NotImplementedError

    async def get_additional_data(self) -> Dict[str, Any]:
        return {}

    async def has_active_request(self, user_id: int) -> bool:
        """
        Проверка активной заявки через Store-слой (с учётом БД).
        При отсутствии стора используем старую логику по памяти.
        """
        try:
            import state as _state_for_store

            store = getattr(_state_for_store, "request_store", None)
        except Exception:
            logger.debug("BaseRequestModal has_active_request: не удалось получить request_store", exc_info=True)
            store = None

        if store is None:
            from state import active_requests  # локальный импорт, чтобы избежать циклов

            return any(
                (req or {}).get("user_id") == user_id for req in (active_requests or {}).values()
            )

        return await store.has_active_for_user(user_id)

    async def save_request(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
        validated_data: Dict[str, Any],
        additional_data: Dict[str, Any],
    ):
        embed_dict = message.embeds[0].to_dict() if message.embeds else {}
        if not message.embeds:
            logger.warning("Сообщение заявки без embed после отправки (message_id=%s)", message.id)
        data = {
            "user_id": interaction.user.id,
            "message_id": message.id,
            "message_link": message.jump_url,
            "embed": embed_dict,
            "request_type": self.request_type.value,
            "created_at": datetime.now().isoformat(),
            **validated_data,
            **additional_data,
        }
        try:
            import state as _state_for_store

            store = getattr(_state_for_store, "request_store", None)
        except Exception:
            logger.debug("BaseRequestModal save_request: не удалось получить request_store", exc_info=True)
            store = None

        if store is None:
            # Fallback на прежнюю схему, если store недоступен (например, в ранних тестах).
            from state import active_requests  # локальный импорт
            from database import save_request as _save_request_legacy

            active_requests[message.id] = data
            await _save_request_legacy("requests", message.id, data)
        else:
            await store.upsert_active(message.id, data)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if await self.has_active_request(interaction.user.id):
                await interaction.response.send_message("❌ У вас уже есть активная заявка!", ephemeral=True)
                return
            success, result = await self.validate_all()
            if not success:
                await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            embed = await self.create_embed(result, interaction)
            additional_data = await self.get_additional_data()


            from views.request_view import RequestView

            view = RequestView(
                user_id=interaction.user.id,
                validated_data=result,
                request_type=self.request_type,
                **additional_data
            )
            if state.bot is None:
                logger.error("state.bot не инициализирован")
                await interaction.followup.send("❌ Ошибка конфигурации: бот не готов.", ephemeral=True)
                return
            channel = state.bot.get_channel(Config.REQUEST_CHANNEL_ID)
            if not channel:
                logger.error("канал заявок %s не найден", Config.REQUEST_CHANNEL_ID)
                await interaction.followup.send("❌ Ошибка конфигурации: канал заявок не найден", ephemeral=True)
                return
            from utils.rate_limiter import safe_send
            message = await safe_send(
                channel,
                content=interaction.user.mention,
                embed=embed,
                view=view,
            )
            try:
                await self.save_request(interaction, message, result, additional_data)
            except Exception as save_err:
                logger.error("Ошибка сохранения заявки после отправки в канал: %s", save_err, exc_info=True)
                try:
                    await message.delete()
                except Exception as del_err:
                    logger.warning("Не удалось удалить сообщение заявки при откате: %s", del_err)
                await interaction.followup.send(ErrorMessages.GENERIC, ephemeral=True)
                return
            await interaction.followup.send(SuccessMessages.REQUEST_SENT, ephemeral=True)
            logger.info("создана новая заявка %s от %s", self.request_type.value, interaction.user.id)
        except Exception as e:
            logger.error("ошибка при отправке заявки: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, ErrorMessages.GENERIC, ephemeral=True)