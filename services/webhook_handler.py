import re
import logging
import asyncio
import discord

from config import Config
from state import active_firing_requests, active_promotion_requests
from database import save_request
from views.firing_view import FiringView
from views.promotion_view import PromotionView
from models import FiringRequest, PromotionRequest
from constants import WebhookPatterns

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Обработчик вебхуков (рапорты увольнение/повышение)."""

    def __init__(self, bot):
        self.bot = bot
        self._compile_patterns()

    def _compile_patterns(self):
        self.firing_patterns = {
            key: re.compile(pattern, re.IGNORECASE)
            for key, pattern in WebhookPatterns.FIRING.items()
        }
        self.promotion_patterns = {
            key: re.compile(pattern, re.IGNORECASE)
            for key, pattern in WebhookPatterns.PROMOTION.items()
        }
        self.common_patterns = {
            key: re.compile(pattern, re.IGNORECASE)
            for key, pattern in WebhookPatterns.COMMON.items()
        }

    async def process_webhook(self, message: discord.Message):
        try:
            if not message or not message.embeds:
                return

            embed = message.embeds[0]
            title = (embed.title or "").strip()

            # Увольнение
            if title == "РАПОРТ ОБ УВОЛЬНЕНИИ":
                await self.process_firing(message, embed)
                return

            # Повышение (ищем характерный формат поля)
            for field in (embed.fields or []):
                field_name = (field.name or "").strip()
                if "👤" in field_name and "|" in field_name:
                    await self.process_promotion(message, embed)
                    return

        except Exception as e:
            logger.error(
                "❌ Ошибка в process_webhook (msg_id=%s, channel_id=%s): %s",
                getattr(message, "id", "unknown"),
                getattr(getattr(message, "channel", None), "id", "unknown"),
                e,
                exc_info=True,
            )

    async def process_firing(self, message: discord.Message, embed: discord.Embed):
        data = self._parse_firing_embed(embed)
        if not data:
            logger.error("❌ Не удалось распарсить рапорт об увольнении (msg_id=%s)", message.id)
            return

        try:
            from modals.firing_apply_modal import _build_firing_embed
            from datetime import datetime

            created_at = datetime.now()
            with_recovery = "с возможностью восстановления" in (data.get("recovery_option") or "")
            new_embed = _build_firing_embed(
                discord_id=data["discord_id"],
                full_name=data["full_name"],
                rank=data.get("rank") or "—",
                photo_link=data.get("photo_link") or "—",
                with_recovery=with_recovery,
                reason=data["reason"],
                created_at=created_at,
            )
            view = FiringView(user_id=data["discord_id"])

            role_mention = f"<@&{Config.FIRING_STAFF_ROLE_ID}>"

            bot_msg = await message.channel.send(
                content=role_mention,
                embed=new_embed,
                view=view
            )

            firing_request = FiringRequest(
                discord_id=data["discord_id"],
                full_name=data["full_name"],
                rank=data.get("rank") or "",
                reason=data["reason"],
                recovery_option=data.get("recovery_option", "без возможности восстановления"),
                photo_link=data.get("photo_link"),
            )
            firing_request.message_link = bot_msg.jump_url

            active_firing_requests[bot_msg.id] = firing_request.to_dict()

            await asyncio.to_thread(
                save_request,
                "firing_requests",
                bot_msg.id,
                firing_request.to_dict()
            )

            # Удаляем исходное webhook-сообщение
            try:
                await message.delete()
            except discord.NotFound:
                logger.info("Webhook-сообщение увольнения уже удалено (msg_id=%s)", message.id)
            except discord.Forbidden:
                logger.warning("Нет прав удалить webhook-сообщение увольнения (msg_id=%s)", message.id)
            except discord.HTTPException as e:
                logger.warning("HTTP ошибка при удалении webhook-сообщения увольнения %s: %s", message.id, e)

            logger.info(
                "✅ Создан рапорт на увольнение: user_id=%s, msg_id=%s",
                data["discord_id"],
                bot_msg.id
            )

        except discord.Forbidden:
            logger.error("❌ Нет прав отправить рапорт на увольнение в канал %s", getattr(message.channel, "id", "unknown"))
        except discord.HTTPException as e:
            logger.error("❌ HTTP ошибка при обработке увольнения (src_msg=%s): %s", message.id, e, exc_info=True)
        except Exception as e:
            logger.error("❌ Ошибка process_firing (src_msg=%s): %s", message.id, e, exc_info=True)

    async def process_promotion(self, message: discord.Message, embed: discord.Embed):
        data = self._parse_promotion_embed(embed)
        if not data:
            logger.error("❌ Не удалось распарсить рапорт на повышение (msg_id=%s)", message.id)
            return

        try:
            new_embed = discord.Embed.from_dict(embed.to_dict())
            view = PromotionView(
                user_id=data["discord_id"],
                new_rank=data["new_rank"],
                full_name=data["full_name"],
                message_id=0  # временно, обновим после отправки
            )

            bot_msg = await message.channel.send(embed=new_embed, view=view)

            promo_request = PromotionRequest(
                discord_id=data["discord_id"],
                full_name=data["full_name"],
                new_rank=data["new_rank"],
                message_link=bot_msg.jump_url
            )

            active_promotion_requests[bot_msg.id] = promo_request.to_dict()

            await asyncio.to_thread(
                save_request,
                "promotion_requests",
                bot_msg.id,
                promo_request.to_dict()
            )

            # Обновляем ID сообщения в view (нужно для дальнейших действий)
            view.message_id = bot_msg.id
            try:
                await bot_msg.edit(view=view)
            except discord.NotFound:
                logger.warning("Сообщение повышения исчезло до обновления view (msg_id=%s)", bot_msg.id)
            except discord.Forbidden:
                logger.warning("Нет прав обновить view у сообщения повышения (msg_id=%s)", bot_msg.id)
            except discord.HTTPException as e:
                logger.warning("HTTP ошибка при обновлении view у повышения (msg_id=%s): %s", bot_msg.id, e)

            # Удаляем исходное webhook-сообщение
            try:
                await message.delete()
            except discord.NotFound:
                logger.info("Webhook-сообщение повышения уже удалено (msg_id=%s)", message.id)
            except discord.Forbidden:
                logger.warning("Нет прав удалить webhook-сообщение повышения (msg_id=%s)", message.id)
            except discord.HTTPException as e:
                logger.warning("HTTP ошибка при удалении webhook-сообщения повышения %s: %s", message.id, e)

            logger.info(
                "✅ Создан рапорт на повышение: user_id=%s, rank='%s', msg_id=%s",
                data["discord_id"],
                data["new_rank"],
                bot_msg.id
            )

        except discord.Forbidden:
            logger.error("❌ Нет прав отправить рапорт на повышение в канал %s", getattr(message.channel, "id", "unknown"))
        except discord.HTTPException as e:
            logger.error("❌ HTTP ошибка при обработке повышения (src_msg=%s): %s", message.id, e, exc_info=True)
        except Exception as e:
            logger.error("❌ Ошибка process_promotion (src_msg=%s): %s", message.id, e, exc_info=True)

    def _parse_firing_embed(self, embed: discord.Embed):
        """Парсит embed увольнения"""
        description = (embed.description or "").strip()
        if not description:
            logger.error("Нет описания в embed увольнения")
            return None

        # 1) Ищем ID пользователя
        discord_id = None
        match = self.firing_patterns["user_id"].search(description)
        if match:
            try:
                discord_id = int(match.group(1))
            except (TypeError, ValueError):
                logger.error("Некорректный Discord ID в увольнении: %r", match.group(1))
                return None

        if not discord_id:
            logger.error("Не найден ID пользователя в рапорте на увольнение")
            return None

        # 2) Имя
        full_name = "Сотрудник"
        match = self.firing_patterns["full_name"].search(description)
        if match:
            full_name = (match.group(1) or "").strip() or "Сотрудник"
            logger.info("✅ Найдено имя (увольнение): %s", full_name)
        else:
            match = self.firing_patterns.get("full_name_alt")
            if match:
                m2 = match.search(description)
                if m2:
                    full_name = (m2.group(1) or "").strip() or "Сотрудник"
                    logger.info("✅ Найдено имя (альт, увольнение): %s", full_name)
                else:
                    logger.warning("⚠️ Имя не найдено в увольнении, используем 'Сотрудник'")

        # 3) Причина
        reason = "псж"
        match = self.firing_patterns["reason"].search(description)
        if match:
            reason = (match.group(1) or "").strip() or "псж"

        # 4) Опция восстановления
        recovery_option = "без возможности восстановления"
        match = self.firing_patterns["recovery"].search(description)
        if match:
            recovery_option = (match.group(1) or "").strip() or recovery_option

        logger.info(
            "📝 Данные увольнения: id=%s, имя='%s', причина='%s', восстановление='%s'",
            discord_id,
            full_name,
            reason,
            recovery_option,
        )

        return {
            "discord_id": discord_id,
            "full_name": full_name,
            "reason": reason,
            "recovery_option": recovery_option,
        }

    def _parse_promotion_embed(self, embed: discord.Embed):
        discord_id = None
        new_rank = None
        full_name = None

        fields = list(embed.fields or [])

        # 1) Ищем ID в полях
        for field in fields:
            field_value = (field.value or "").strip()
            if not field_value:
                continue

            match = self.promotion_patterns["user_id"].search(field_value)
            if match:
                try:
                    discord_id = int(match.group(1))
                    break
                except (TypeError, ValueError):
                    logger.error("Некорректный Discord ID в поле повышения: %r", match.group(1))
                    return None

        # 2) Если не нашли — ищем в описании
        if not discord_id and embed.description:
            match = self.promotion_patterns["user_id_desc"].search(embed.description)
            if match:
                try:
                    discord_id = int(match.group(1))
                except (TypeError, ValueError):
                    logger.error("Некорректный Discord ID в описании повышения: %r", match.group(1))
                    return None

        if not discord_id:
            logger.error("Не найден ID пользователя в рапорте на повышение")
            return None

        # 3) Ищем звание и имя в полях с 👤
        for field in fields:
            field_name = (field.name or "").strip()
            if not field_name or "👤" not in field_name:
                continue

            match = self.promotion_patterns["rank_and_name"].search(field_name)
            if match:
                full_name = (match.group(1) or "").strip() or "сотрудник"
                new_rank = (match.group(2) or "").strip()
                break

        if not new_rank:
            logger.error("Не найдено звание в рапорте на повышение")
            return None

        logger.info(
            "📝 Данные повышения: id=%s, имя='%s', звание='%s'",
            discord_id,
            full_name or "сотрудник",
            new_rank
        )

        return {
            "discord_id": discord_id,
            "full_name": full_name or "сотрудник",
            "new_rank": new_rank
        }