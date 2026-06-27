import discord
from discord.ui import Modal, TextInput
import logging

from views.message_texts import ErrorMessages
from utils.interaction_helpers import safe_followup_or_response
from services.warehouse_session import WarehouseSession
from data.warehouse_items import WAREHOUSE_ITEMS

logger = logging.getLogger(__name__)


def _find_item_limit(item_name: str):
    try:
        for category_data in WAREHOUSE_ITEMS.values():
            if not isinstance(category_data, dict):
                continue

            items = category_data.get("items", {})
            if item_name not in items:
                continue

            raw = items[item_name]

            if isinstance(raw, int):
                return raw

            if isinstance(raw, dict):
                max_q = raw.get("max_quantity")
                if isinstance(max_q, int):
                    return max_q

                max_q = raw.get("max")
                if isinstance(max_q, int):
                    return max_q

            return None
    except Exception:
        logger.debug("_find_item_limit: ошибка при разборе лимита предмета", exc_info=True)
        return None

    return None


class WarehouseEditModal(Modal):
    def __init__(
        self,
        user_id: int | None = None,
        item_index: int | None = None,
        category: str | None = None,
        item_name: str | None = None,
        current_quantity: int | None = None,
        session_key=None,
        allowed_user_id: int | None = None,
        request_owner_id: int | None = None,
        editing_request_message_id: int | None = None,
        mode: str = "request",
        current_item: dict | None = None,
        **kwargs,
    ):
        self.allowed_user_id = allowed_user_id if allowed_user_id is not None else user_id
        self.session_key = session_key if session_key is not None else user_id
        self.item_index = item_index
        self.request_owner_id = request_owner_id
        self.editing_request_message_id = editing_request_message_id
        self.mode = mode if mode in ("request", "issue") else "request"

        self.fallback_category = category
        self.fallback_item_name = item_name
        self.fallback_quantity = int(current_quantity or 1)

        if current_item is not None:
            self.current_item = current_item
        elif category and item_name:
            self.current_item = {
                "category": category,
                "item": item_name,
                "quantity": self.fallback_quantity,
            }
        else:
            self.current_item = None

        super().__init__(title="✏️ РЕДАКТИРОВАТЬ ПРЕДМЕТ")

        if self.current_item:
            self.quantity = TextInput(
                label=f"Количество ({self.current_item['item']})",
                default=str(self.current_item.get("quantity", 1)),
                placeholder="Введите новое количество",
                max_length=6,
                required=True,
            )
            self.add_item(self.quantity)

    async def _resolve_item_index(self, session_key) -> int | None:
        items = await WarehouseSession.get_items(session_key)

        if isinstance(self.item_index, int) and 0 <= self.item_index < len(items):
            return self.item_index

        for idx, it in enumerate(items):
            if (
                it.get("category") == self.fallback_category
                and it.get("item") == self.fallback_item_name
            ):
                return idx

        return None

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.allowed_user_id is None:
                self.allowed_user_id = interaction.user.id

            if self.session_key is None:
                self.session_key = interaction.user.id

            if interaction.user.id != self.allowed_user_id:
                await interaction.response.send_message("❌ Это не ваша корзина.", ephemeral=True)
                return

            if not self.current_item:
                await interaction.response.send_message("❌ Предмет не найден в корзине.", ephemeral=True)
                return

            qty_text = str(self.quantity.value).strip()
            if not qty_text.isdigit():
                await interaction.response.send_message("❌ Количество должно быть числом.", ephemeral=True)
                return

            new_qty = int(qty_text)
            if new_qty <= 0:
                await interaction.response.send_message("❌ Количество должно быть больше 0.", ephemeral=True)
                return

            resolved_index = await self._resolve_item_index(self.session_key)
            if resolved_index is None:
                await interaction.response.send_message(
                    "❌ Не удалось найти предмет в вашей корзине.",
                    ephemeral=True,
                )
                return

            self.item_index = resolved_index

            items = await WarehouseSession.get_items(self.session_key)
            if not (0 <= self.item_index < len(items)):
                await interaction.response.send_message("❌ Предмет больше не найден в корзине.", ephemeral=True)
                return

            actual_item = items[self.item_index]
            item_name = actual_item.get("item")
            category_name = actual_item.get("category")

            if not item_name or not category_name:
                await interaction.response.send_message("❌ Некорректные данные предмета в корзине.", ephemeral=True)
                return

            max_item = _find_item_limit(item_name)
            if isinstance(max_item, int) and new_qty > max_item:
                await interaction.response.send_message(
                    f"❌ Для предмета **{item_name}** максимум: **{max_item}** шт.",
                    ephemeral=True,
                )
                return

            category_cfg = WAREHOUSE_ITEMS.get(category_name, {})
            max_total = None
            if isinstance(category_cfg, dict):
                max_total = category_cfg.get("max_total")

            if isinstance(max_total, int):
                category_total_without_current = 0
                for idx, it in enumerate(items):
                    if idx == self.item_index:
                        continue
                    if it.get("category") == category_name:
                        try:
                            category_total_without_current += int(it.get("quantity", 0))
                        except (TypeError, ValueError):
                            continue

                new_category_total = category_total_without_current + new_qty
                if new_category_total > max_total:
                    await interaction.response.send_message(
                        f"❌ Превышен лимит категории **{category_name}**: "
                        f"максимум **{max_total}** шт. "
                        f"(сейчас будет **{new_category_total}**).",
                        ephemeral=True,
                    )
                    return

            items[self.item_index]["quantity"] = new_qty

            if self.editing_request_message_id is not None and self.session_key:
                await interaction.response.defer(ephemeral=True)
                from views.warehouse_request_buttons import build_edit_cart_embed
                from views.warehouse_actions import WarehouseActionView
                is_staff = self.mode == "issue"
                cart_embed = await build_edit_cart_embed(self.session_key, is_staff)
                view = WarehouseActionView(
                    session_key=self.session_key,
                    request_owner_id=self.request_owner_id,
                    editing_request_message_id=self.editing_request_message_id,
                    mode=self.mode,
                )
                try:
                    await interaction.followup.edit_message(
                        message_id=interaction.message.id,
                        content=None,
                        embed=cart_embed,
                        view=view,
                    )
                    await interaction.followup.send(
                        f"✅ Обновлено: **{item_name}** — теперь **{new_qty}** шт. Нажми **ОТПРАВИТЬ**, когда будешь готов.",
                        ephemeral=True,
                    )
                except (discord.NotFound, discord.HTTPException):
                    await interaction.followup.send(
                        f"✅ Обновлено: **{item_name}** — теперь **{new_qty}** шт.",
                        ephemeral=True,
                    )
            else:
                await interaction.response.send_message(
                    f"✅ Обновлено: **{item_name}** — теперь **{new_qty}** шт.",
                    ephemeral=True,
                )

        except Exception as e:
            logger.error("Ошибка в WarehouseEditModal.on_submit: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, ErrorMessages.GENERIC, ephemeral=True)