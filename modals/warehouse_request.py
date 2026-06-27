import discord
from discord.ui import Modal, TextInput
import logging
from data.warehouse_items import WAREHOUSE_ITEMS, CATEGORY_EMOJIS
from utils.interaction_helpers import safe_followup_or_response

logger = logging.getLogger(__name__)


class QuantityModal(Modal):
    def __init__(
        self,
        category: str,
        item_name: str,
        session_key=None,
        request_owner_id: int | None = None,
        editing_request_message_id: int | None = None,
    ):
        emoji = CATEGORY_EMOJIS.get(category, "📦")
        super().__init__(title=f"{emoji} {item_name}")
        self.category = category
        self.item_name = item_name
        self.session_key = session_key
        self.request_owner_id = request_owner_id
        self.editing_request_message_id = editing_request_message_id

        item_data = WAREHOUSE_ITEMS[category]["items"][item_name]

        if isinstance(item_data, int):
            max_value = item_data
            unit = "шт"
        else:
            max_value = item_data.get("max", 999)
            unit = item_data.get("unit", "шт")

        self.quantity = TextInput(
            label="Количество",
            placeholder=f"От 1 до {max_value} {unit}",
            required=True,
            min_length=1,
            max_length=4
        )
        self.add_item(self.quantity)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            quantity = int(self.quantity.value)

            item_data = WAREHOUSE_ITEMS[self.category]["items"][self.item_name]
            if isinstance(item_data, int):
                max_value = item_data
            else:
                max_value = item_data.get("max", 999)

            if quantity > max_value:
                await interaction.response.send_message(
                    f"❌ **Ошибка:** нельзя взять больше {max_value}!",
                    ephemeral=True
                )
                return

            if quantity < 1:
                await interaction.response.send_message(
                    "❌ **Ошибка:** количество должно быть хотя бы 1",
                    ephemeral=True
                )
                return

            from services.warehouse_session import WarehouseSession

            session_key = self.session_key if self.session_key is not None else interaction.user.id

            success, error_msg = await WarehouseSession.add_item(
                session_key,
                self.category,
                self.item_name,
                quantity
            )

            if not success:
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                f"✅ **{self.item_name}** — добавлено в корзину: **{quantity}** шт.",
                ephemeral=True,
            )

        except ValueError:
            await interaction.response.send_message(
                "❌ **Ошибка:** введи число!",
                ephemeral=True
            )
        except Exception as e:
            logger.error("Ошибка QuantityModal: %s", e, exc_info=True)
            await safe_followup_or_response(
                interaction,
                "❌ **Ошибка:** что-то пошло не так",
                ephemeral=True,
            )