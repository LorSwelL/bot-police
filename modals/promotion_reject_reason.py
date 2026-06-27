import logging

from config import Config
from state import active_promotion_requests
from .base_reject import BaseRejectModal

logger = logging.getLogger(__name__)


class PromotionRejectReasonModal(BaseRejectModal):

    @classmethod
    def get_modal_title(cls):
        return "отклонение рапорта на повышение"

    async def get_staff_role_id(self, interaction):

        channel = getattr(interaction, "channel", None)
        if not channel or not getattr(channel, "id", None):
            return 0
        role_ids = list(Config.PROMOTION_CHANNELS.get(channel.id, []) or [])
        return int(role_ids[0]) if role_ids else 0

    async def get_allowed_role_ids(self, interaction):
        channel = getattr(interaction, "channel", None)
        if not channel or not getattr(channel, "id", None):
            return []
        role_ids = list(Config.PROMOTION_CHANNELS.get(channel.id, []) or [])
        return [int(rid) for rid in role_ids if int(rid) != 0]

    async def get_request_data(self, message_id):
        try:
            import state as _state_for_store  # type: ignore
        except Exception:
            logger.debug("PromotionRejectReasonModal: не удалось импортировать state", exc_info=True)
            _state_for_store = None

        store = None
        if _state_for_store is not None:
            try:
                store = getattr(_state_for_store, "promotion_store", None)
            except Exception as e:
                logger.warning(
                    "PromotionRejectReasonModal: не удалось получить promotion_store: %s",
                    e,
                    exc_info=True,
                )
                store = None

        if store is not None:
            try:
                data = store.get_by_message_id(message_id)
            except Exception as e:
                logger.warning(
                    "PromotionRejectReasonModal: ошибка чтения из Store для message_id=%s: %s",
                    message_id,
                    e,
                    exc_info=True,
                )
                data = None
            if data:
                return data

        return active_promotion_requests.get(message_id)

    def get_view_class(self):
        from views.promotion_view import PromotionView
        return PromotionView

    def get_state_dict(self):
        return active_promotion_requests

    def get_table_name(self):
        return "promotion_requests"

    def get_notification_title(self):
        return "❌ Рапорт на повышение отклонён"

    def get_item_name(self):
        return "рапорт"

    async def get_view_instance(self, interaction, request_data):
        from views.promotion_view import PromotionView
        view = PromotionView(
            user_id=self.user_id,
            new_rank=self.additional_data.get("new_rank", ""),
            full_name=self.additional_data.get("full_name", ""),
            message_id=self.message_id
        )
        for item in view.children:
            item.disabled = True
        return view

    async def on_submit(self, interaction):
        msg = None
        try:
            if interaction.channel:
                msg = await interaction.channel.fetch_message(self.message_id)
        except Exception as e:
            logger.warning(
                "Не удалось получить сообщение рапорта повышения %s перед отклонением: %s",
                self.message_id,
                e,
                exc_info=True,
            )

        if msg and msg.embeds:
            embed = msg.embeds[0]
            for field in embed.fields:
                name = (field.name or "").strip().lower()
                value = (field.value or "").strip().lower()
                if "статус" in name:
                    if "принят" in value or "одоб" in value:
                        await interaction.response.send_message(
                            "⚠️ Этот рапорт уже обработан и не может быть отклонён.",
                            ephemeral=True,
                        )
                        return
                    if "отклон" in value:
                        await interaction.response.send_message(
                            "⚠️ Этот рапорт уже отклонён.",
                            ephemeral=True,
                        )
                        return

        if self.message_id not in active_promotion_requests and msg:
            try:
                active_promotion_requests[self.message_id] = {
                    "discord_id": self.user_id,
                    "full_name": self.additional_data.get("full_name", "") or "сотрудник",
                    "new_rank": self.additional_data.get("new_rank", "") or "",
                    "message_link": getattr(msg, "jump_url", ""),
                }
                logger.warning(
                    "Повышение (reject): рапорт %s восстановлен из view-параметров (state/БД пусто)",
                    self.message_id
                )
            except Exception as e:
                logger.warning(
                    "Не удалось восстановить рапорт повышения %s перед отклонением: %s",
                    self.message_id,
                    e,
                    exc_info=True
                )

        await super().on_submit(interaction)