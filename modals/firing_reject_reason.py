import logging

from config import Config
from .base_reject import BaseRejectModal

logger = logging.getLogger(__name__)


class FiringRejectReasonModal(BaseRejectModal):

    @classmethod
    def get_modal_title(cls):
        return "отклонение рапорта об увольнении"

    async def get_staff_role_id(self, interaction):
        return Config.FIRING_STAFF_ROLE_ID

    async def get_request_data(self, message_id):
        try:
            import state as _state_for_store

            store = getattr(_state_for_store, "firing_store", None)
        except Exception:
            logger.debug("FiringRejectReasonModal get_request_data: не удалось получить firing_store", exc_info=True)
            store = None

        if store is not None:
            return store.get_by_message_id(message_id)

        from state import active_firing_requests  # локальный импорт

        return active_firing_requests.get(message_id)

    def get_view_class(self):
        from views.firing_view import FiringView
        return FiringView

    def get_state_dict(self):
        # Используется как fallback, если Store недоступен.
        from state import active_firing_requests  # локальный импорт

        return active_firing_requests

    def get_table_name(self):
        return "firing_requests"

    def get_notification_title(self):
        return "❌ Рапорт об увольнении отклонён"

    def get_item_name(self):
        return "рапорт"

    async def on_submit(self, interaction):
        msg = None
        try:
            if interaction.channel:
                msg = await interaction.channel.fetch_message(self.message_id)
        except Exception as e:
            logger.warning(
                "Не удалось получить сообщение рапорта увольнения %s перед отклонением: %s",
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
                    if "уволен" in value or "удовлетвор" in value or "одобрен" in value:
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

        await super().on_submit(interaction)