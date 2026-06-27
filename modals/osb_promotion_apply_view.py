# -*- coding: utf-8 -*-

import re
import logging

import discord
from discord.ui import View, Select

from config import Config
from constants import FieldNames, StatusValues, EmbedTitles
from models import PromotionRequest
import state
from state import osb_draft_reports, osb_last_user_data
from database import save_osb_draft, load_osb_draft, delete_osb_draft
from services.worker_queue import get_worker
from services.department_roles import get_dept_role_id
from services.ranks import is_promotion_key_allowed_for_member, get_member_rank_display
from services.promotion_common import build_generic_collector_embed, sort_int_like, has_active_promotion, get_reviewers_mention_content, drop_orphan_promotion_requests_for_user
from utils.promotion_helpers import (
    parse_thanks_lines,
    send_long,
    required_count_from_text,
    normalize_thanks,
    normalize_bonus_links,
    calc_bonus_points,
    requirement_short_label,
    links_word,
)
from utils.interaction_helpers import safe_followup_or_response
from utils.validators import validate_user_link

logger = logging.getLogger(__name__)

OSB_POINTS_MAP = {
    1: 35,   # Участие в поставке
    2: 35,   # Участие в ГМП
    3: 25,   # Участие в отбитии Краза
    4: 20,   # Задержание и арест
    5: 15,   # Составление административного протокола
    6: 25,   # Участие в тренировке
    7: 25,   # Участие в вечерней поверке
    8: 45,   # Реагирование на нападение на тюрьму
    9: 40,   # Пост в ЦГБ или передача задержанных на допрос в ФСБ
    10: 25,  # Принятие заявления о преступлении
    11: 50,  # Проведение служебной проверки
    12: 25,  # Участие в проверке подразделения УВД
    13: 150, # Написание уголовного дела
    14: 15,  # Заполнение любой документации
    15: 25,  # Проведение ОРМ
    16: 20,  # Надзор за посещением строев и поставок
    17: 25,  # Успешное отбитие ограбления квартиры
    18: 50,  # Проведение профилактических бесед
}


PROMOTION_REQUIREMENTS_OSB = {
    "Сержант -> Старший сержант": {
        "points": 400,
        "required": [
            "Подача сейфа документов → 1 шт.",
            "Задержание → 1 шт.",
            "Составление административного протокола → 1 шт.",
            "Проверка состава на поставке → 2 шт.",
            "Участие в любом мероприятии от руководства → 1 шт.",
        ],
    },
    "Старший сержант -> Старшина": {
        "points": 500,
        "required": [
            "Задержание → 1 шт.",
            "Составление административного протокола → 2 шт.",
            "Проверка состава на поставке → 2 шт.",
            "Участие в тренировке от ОРЛС или ОСН \"Гром\" → 1 шт.",
            "Составление приказа о выдаче дисцип. взыскания → 1 шт.",
        ],
    },
    "Старшина -> Прапорщик": {
        "points": 600,
        "required": [
            "Проверка состава на поставке → 2 шт.",
            "Патрулирование с младшим по званию (обучающее) → 30 минут",
            "Участие в отбитии ограбления квартиры/налета/объекта → 3 шт.",
            "Составление приказа о выдаче дисцип. взыскания → 1 шт.",
        ],
    },
    "Прапорщик -> Старший прапорщик": {
        "points": 700,
        "required": [
            "Участие в любом мероприятии от руководства → 1 шт.",
            "Патрулирование с младшим по званию (обучающее) → 30 минут",
            "Участие в отбитии ограбления квартиры/налета/объекта → 3 шт.",
            "Составление приказа о выдаче дисцип. взыскания → 1 шт.",
        ],
    },
    "Старший прапорщик -> Младший лейтенант": {
        "points": 800,
        "required": [
            "Подача сейфа документов с военным билетом → 1 шт.",
            "Составление административного протокола → 3 шт.",
            "Задержание → 2 шт.",
            "Участие в отбитии ограбления квартиры/налета/объекта → 3 шт.",
            "Составление приказа о выдаче дисцип. взыскания → 1 шт.",
        ],
    },
    "Младший лейтенант -> Лейтенант": {
        "points": 900,
        "required": [
            "Составление административного протокола → 3 шт.",
            "Проверка состава на поставке → 3 шт.",
            "Задержание → 2 шт.",
            "Составление приказа о выдаче дисцип. взыскания → 2 шт.",
        ],
    },
    "Лейтенант -> Старший лейтенант": {
        "points": 1000,
        "required": [
            "Проверка состава на поставке → 3 шт.",
            "Участие в любом мероприятии от руководства → 1 шт.",
            "Участие в тренировке / арене → 1 шт.",
            "Задержание → 2 шт.",
            "Составление приказа о выдаче дисцип. взыскания → 3 шт.",
        ],
    },
    "Старший лейтенант -> Капитан": {
        "points": 1100,
        "required": [
            "Составление административного протокола → 3 шт.",
            "Участие в любом мероприятии от руководства → 1 шт.",
            "Общая проверка личного состава → 1 шт.",
            "Задержание → 3 шт.",
            "Составление приказа о выдаче дисцип. взыскания → 3 шт.",
        ],
    },
}


OSB_BONUS_LABELS = [
    (1, "Поставка (35)"), (2, "ГМП (35)"), (3, "Отбитие Краза (25)"), (4, "Задержание/арест (20)"),
    (5, "Адм. протокол (15)"), (6, "Тренировка (25)"), (7, "Вечерняя поверка (25)"),
    (8, "Нападение на тюрьму (45)"), (9, "ЦГБ/ФСБ (40)"),
    (10, "Заявление о преступлении (25)"), (11, "Служебная проверка (50)"),
    (12, "Проверка подразделения УВД (25)"), (13, "Уголовное дело (150)"),
    (14, "Документация (15)"), (15, "ОРМ (25)"),     (16, "Надзор за строями (20)"),
    (17, "Отбитие ограбления квартиры (25)"),
    (18, "Профилактические беседы (50)"),
]

OSB_POINTS_TEXT = (
    "**Общие:** 1. Поставка 35 | 2. ГМП 35 | 3. Краз 25 | 4. Задержание 20 | 5. Адм. протокол 15 | "
    "6. Тренировка 25 | 7. Поверка 25 | 8. Нападение на тюрьму 45 | 9. ЦГБ/ФСБ 40.\n"
    "**Только ОСБ:** 10. Заявление 25 | 11. Служебная проверка 50 | 12. Проверка УВД 25 | "
    "13. Уголовное дело 150 | 14. Документация 15 | 15. ОРМ 25 | 16. Надзор за строями 20 | 17. Отбитие ограбления 25 | "
    "18. Проведение профилактических бесед 50."
)

OSB_POINTS_FIELDS = [
    ("Общие (типы 1–9)", "1. Поставка 35 | 2. ГМП 35 | 3. Краз 25 | 4. Задержание 20 | 5. Адм. протокол 15 | 6. Тренировка 25 | 7. Поверка 25 | 8. Нападение на тюрьму 45 | 9. ЦГБ/ФСБ 40."),
    ("Только ОСБ (типы 10–18)", "10. Заявление 25 | 11. Служебная проверка 50 | 12. Проверка УВД 25 | 13. Уголовное дело 150 | 14. Документация 15 | 15. ОРМ 25 | 16. Надзор за строями 20 | 17. Отбитие ограбления 25 | 18. Проведение профилактических бесед 50."),
]
def _build_collector_embed(draft: dict) -> discord.Embed:
    return build_generic_collector_embed(
        draft,
        promotion_requirements=PROMOTION_REQUIREMENTS_OSB,
        points_map=OSB_POINTS_MAP,
        department_label="ОСБ",
    )


class OsbLinksModal(discord.ui.Modal, title="Ссылки (ОСБ)"):
    def __init__(self, label: str, requirement_index: int | None, bonus_type: int | None, user_id: int, is_bulk: bool = False):
        super().__init__(timeout=None)
        self.requirement_index = requirement_index
        self.bonus_type = bonus_type
        self.user_id = user_id
        self.is_bulk = is_bulk
        if requirement_index is not None:
            placeholder = "По одной ссылке в строку."
        elif bonus_type is not None:
            if is_bulk:
                placeholder = "Формат: тип количество ссылка. Пример: 8 10 https://..."
            else:
                placeholder = "По одной ссылке в строку."
        else:
            placeholder = "По одной в строке."
        if len(placeholder) > 100:
            placeholder = placeholder[:97] + "..."
        self.links_field = discord.ui.TextInput(
            label=label[:45],
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
            placeholder=placeholder[:100],
        )
        self.add_item(self.links_field)
        
        if bonus_type is not None and not is_bulk:
            self.quantity_field = discord.ui.TextInput(
                label="Количество фиксаций в ссылке",
                style=discord.TextStyle.short,
                required=False,
                max_length=5,
                placeholder="1",
                default="1",
            )
            self.add_item(self.quantity_field)
        else:
            self.quantity_field = None

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            if interaction.user and interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
                return
            draft = osb_draft_reports.get(self.user_id)
            if not draft:
                draft = await get_worker().submit(load_osb_draft, self.user_id)
                if draft:
                    osb_draft_reports[self.user_id] = draft
            if not draft:
                await interaction.response.send_message("Сессия истекла. Начните рапорт заново или нажмите «Продолжить мой рапорт».", ephemeral=True)
                return
            raw = (self.links_field.value or "").strip()
            added = 0
            added_items = 0
            if self.requirement_index is not None:
                urls = [s.strip() for s in raw.splitlines() if s.strip() and validate_user_link(s.strip())]
                draft.setdefault("requirement_links", {})[self.requirement_index] = draft.get("requirement_links", {}).get(self.requirement_index, []) + urls
                added = len(urls)
                added_items = added
            elif self.bonus_type is not None:
                default_qty = 1
                if self.quantity_field is not None:
                    try:
                        default_qty = max(1, int((self.quantity_field.value or "1").strip()))
                    except ValueError:
                        default_qty = 1
                
                if self.is_bulk:
                    for line in raw.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split(None, 2)
                        typ = self.bonus_type
                        qty = 1
                        url = line
                        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
                            typ = int(parts[0])
                            if 1 <= typ <= 18:
                                qty = max(1, int(parts[1]))
                                url = parts[2].strip()
                            else:
                                typ = self.bonus_type
                        elif len(parts) >= 2 and parts[0].isdigit():
                            n = int(parts[0])
                            if 1 <= n <= 18:
                                typ = n
                                url = parts[1].strip()
                        if url and validate_user_link(url):
                            draft.setdefault("bonus_links", {})[typ] = draft.get("bonus_links", {}).get(typ, []) + [[url, qty]]
                            added += 1
                            added_items += qty
                else:
                    for line in raw.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        if validate_user_link(line):
                            draft.setdefault("bonus_links", {})[self.bonus_type] = draft.get("bonus_links", {}).get(self.bonus_type, []) + [[line, default_qty]]
                            added += 1
                            added_items += default_qty
            ch_id = draft.get("channel_id")
            msg_id = draft.get("message_id")
            ephemeral_msg = draft.get("_ephemeral_msg")
            snapshot = {k: v for k, v in draft.items() if k != "_ephemeral_msg"}
            get_worker().submit_fire(save_osb_draft, self.user_id, snapshot)
            if not ephemeral_msg and ch_id and msg_id and interaction.guild:
                ch = None
                cache = getattr(state, "channel_cache", None)
                if cache:
                    ch = await cache.get_channel(ch_id)
                if ch is None:
                    ch = interaction.guild.get_channel(ch_id)
                if ch:
                    try:
                        msg = await ch.fetch_message(msg_id)
                        await msg.edit(embed=_build_collector_embed(draft))
                    except Exception as e:
                        logger.warning("Не обновить сообщение сбора ОСБ: %s", e)
            embed = _build_collector_embed(draft)
            view = OsbCollectorView(draft.get("promotion_key", ""), self.user_id)
            await interaction.response.defer(ephemeral=True)
            if added_items != added:
                content_full = "Добавлено %s: **%s** (всего **%s** фиксаций). Баллы пересчитаны." % (links_word(added), added, added_items)
            else:
                content_full = "Добавлено %s: **%s**. Баллы пересчитаны. Ниже — актуальное состояние." % (links_word(added), added)
            if interaction.message:
                try:
                    await interaction.message.edit(content=content_full, embed=embed, view=view)
                except Exception:
                    logger.debug("OsbLinksModal: не удалось отредактировать сообщение, fallback на followup", exc_info=True)
                    await interaction.followup.send(content=content_full, embed=embed, view=view, ephemeral=True)
            else:
                await interaction.followup.send("Добавлено %s: **%s**. Закройте это уведомление. Состояние обновится при следующем действии в сборщике." % (links_word(added), added), ephemeral=True)
        except Exception as e:
            logger.error("Ошибка OsbLinksModal: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, "Ошибка.", ephemeral=True)


class OsbThanksModal(discord.ui.Modal, title="Благодарности и поощрения (ОСБ)"):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.links_field = discord.ui.TextInput(
            label="Баллы и ссылки",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000,
            placeholder="В каждой строке: баллы и ссылка. Пример: 10 https://...",
        )
        self.add_item(self.links_field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            if interaction.user and interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
                return
            draft = osb_draft_reports.get(self.user_id)
            if not draft:
                draft = await get_worker().submit(load_osb_draft, self.user_id)
                if draft:
                    osb_draft_reports[self.user_id] = draft
            if not draft:
                await interaction.response.send_message("Сессия истекла. Начните рапорт заново.", ephemeral=True)
                return
            raw = (self.links_field.value or "").strip()
            if raw:
                draft["thanks_links"] = parse_thanks_lines(raw)
            else:
                draft["thanks_links"] = []
            snapshot = {k: v for k, v in draft.items() if k != "_ephemeral_msg"}
            get_worker().submit_fire(save_osb_draft, self.user_id, snapshot)
            embed = _build_collector_embed(draft)
            view = OsbCollectorView(draft.get("promotion_key", ""), self.user_id)
            await interaction.response.defer(ephemeral=True)
            content_full = "Благодарности сохранены. Ниже — актуальное состояние."
            if interaction.message:
                try:
                    await interaction.message.edit(content=content_full, embed=embed, view=view)
                except Exception:
                    logger.debug("OsbThanksModal: не удалось отредактировать сообщение, fallback на followup", exc_info=True)
                    await interaction.followup.send(content=content_full, embed=embed, view=view, ephemeral=True)
            else:
                await interaction.followup.send("Благодарности сохранены. Закройте это уведомление. Состояние обновится при следующем действии в сборщике.", ephemeral=True)
        except Exception as e:
            logger.error("Ошибка OsbThanksModal: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, "Ошибка.", ephemeral=True)


async def _do_submit_report(draft: dict, interaction: discord.Interaction) -> None:
    ch = None
    if interaction.guild:
        ch_id = draft.get("channel_id")
        if ch_id:
            cache = getattr(state, "channel_cache", None)
            if cache:
                ch = await cache.get_channel(ch_id)
            if ch is None:
                ch = interaction.guild.get_channel(ch_id)
    if not ch or not isinstance(ch, discord.TextChannel):
        await safe_followup_or_response(interaction, "Канал не найден.", ephemeral=True)
        return
    try:
        user_id_int = int(draft.get("discord_id", 0))
    except (TypeError, ValueError):
        await safe_followup_or_response(interaction, "Некорректные данные.", ephemeral=True)
        return
    full_name = draft.get("full_name", "—")
    promotion_key = draft.get("promotion_key", "")
    passport = draft.get("passport", "—")
    requirement_links = draft.get("requirement_links") or {}
    bonus_links = draft.get("bonus_links") or {}
    info = PROMOTION_REQUIREMENTS_OSB.get(promotion_key, {})
    required_list = info.get("required", [])
    points_required = info.get("points", 0)
    
    normalized_bonus = normalize_bonus_links(bonus_links)
    total_bonus = calc_bonus_points(bonus_links, OSB_POINTS_MAP)
    thanks = normalize_thanks(draft.get("thanks_links") or [])
    total_bonus += sum(p for p, _ in thanks)
    
    embed = discord.Embed(
        title=EmbedTitles.PROMOTION,
        color=discord.Color.gold(),
        description="Рапорт на повышение в ОСБ\n\n👤 %s | %s\nDiscord: <@%s> (%s)" % (full_name, promotion_key, user_id_int, user_id_int),
        timestamp=interaction.created_at,
    )
    embed.add_field(name=FieldNames.FULL_NAME, value=full_name, inline=True)
    embed.add_field(name="Паспорт", value=passport, inline=True)
    embed.add_field(name=FieldNames.NEW_RANK, value=promotion_key, inline=False)
    if points_required:
        embed.add_field(name="Баллы", value="**%s** / %s" % (total_bonus, points_required), inline=True)
    embed.add_field(name=FieldNames.STATUS, value=StatusValues.PENDING, inline=True)
    embed.set_footer(text=interaction.user.display_name if interaction.user else "", icon_url=getattr(interaction.user.display_avatar, "url", None) if interaction.user else None)
    from views.promotion_view import PromotionView
    view = PromotionView(user_id=user_id_int, new_rank=promotion_key, full_name=full_name, message_id=0)
    content = get_reviewers_mention_content(ch.id)
    message = await ch.send(content=content or None, embed=embed, view=view)
    promo_request = PromotionRequest(
        discord_id=user_id_int,
        full_name=full_name,
        new_rank=promotion_key,
        message_link=message.jump_url,
    )

    promo_store = getattr(state, "promotion_store", None)
    if promo_store is not None:
        await get_worker().submit(promo_store.upsert_active, message.id, promo_request.to_dict())
    else:
        from state import active_promotion_requests  # локальный импорт
        from database import save_request as _save_promo_legacy

        active_promotion_requests[message.id] = promo_request.to_dict()
        await get_worker().submit(_save_promo_legacy, "promotion_requests", message.id, promo_request.to_dict())

    view.message_id = message.id
    try:
        await message.edit(view=view)
    except Exception as e:
        logger.warning("Не обновить view рапорта ОСБ: %s", e)
    cid, mid = draft.get("channel_id"), draft.get("message_id")
    if cid and mid and interaction.guild:
        try:
            coll_ch = None
            cache = getattr(state, "channel_cache", None)
            if cache:
                coll_ch = await cache.get_channel(cid)
            if coll_ch is None:
                coll_ch = interaction.guild.get_channel(cid)
            if coll_ch:
                msg = await coll_ch.fetch_message(mid)
                await msg.delete()
        except Exception as err:
            logger.warning("Не удалить сообщение-сборщик ОСБ: %s", err)
    try:
        thread = await message.create_thread(name="ОСБ • %s • %s" % (full_name[:80], promotion_key[:30]))
    except discord.HTTPException:
        thread = getattr(message, "thread", None)
        if not thread and interaction.guild:
            try:
                refetched = await ch.fetch_message(message.id)
                thread = getattr(refetched, "thread", None)
            except Exception:
                logger.debug("Osb open_modal: не удалось refetch message для thread", exc_info=True)
                pass
    if thread and (required_list or requirement_links or normalized_bonus or thanks):
        copy_text = (
            "```\n"
            "%s | %s\n"
            "%s\n"
            "Согласно: %s\n"
            "```"
        ) % (full_name, passport, promotion_key, message.jump_url)
        await thread.send(copy_text)
        
        intro = discord.Embed(
            title="📋 Рапорт на повышение ОСБ",
            description=(
                "👤 **%s**\n"
                "🪪 Паспорт: **%s**\n"
                "📈 Повышение: **%s**\n"
                "⭐ Набрано баллов: **%s** из **%s**"
            ) % (full_name, passport, promotion_key, total_bonus, points_required),
            color=discord.Color.blue(),
        )
        await thread.send(embed=intro)
        
        body_parts = []
        for idx, req in enumerate(required_list, start=1):
            urls = requirement_links.get(idx, [])
            body_parts.append("**%s.** %s\n%s" % (idx, req, "\n".join(urls) if urls else "—"))
        
        type_names = {int(typ): name for typ, name in OSB_BONUS_LABELS}
        for t in sort_int_like(normalized_bonus.keys()):
            links = normalized_bonus[t]
            try:
                key = int(t) if str(t).isdigit() else t
            except Exception:
                key = t
            pts_per_item = OSB_POINTS_MAP.get(key, 0)
            total_items = sum(count for url, count in links)
            pts = pts_per_item * total_items
            label = type_names.get(key, "Баллы тип %s" % t)
            links_text = "\n".join("• %s (x%s)" % (url, count) if count > 1 else "• %s" % url for url, count in links)
            body_parts.append("**%s**: %s фикс. = %s б.\n%s" % (label, total_items, pts, links_text if links_text else "—"))
        
        if thanks:
            body_parts.append("**Благодарности и поощрения от начальства**\n" + "\n".join("• %s б.: %s" % (p, u) for p, u in thanks))
        
        if body_parts:
            body_text = "\n\n".join(body_parts)
            await send_long(thread, body_text)
        
        total_embed = discord.Embed(
            title="📊 Итого баллов: %s" % total_bonus,
            description="Требуется: **%s** баллов" % points_required,
            color=discord.Color.green() if total_bonus >= points_required else discord.Color.orange(),
        )
        await thread.send(embed=total_embed)
        
        help_embed = discord.Embed(
            title="📖 Справка по баллам ОСБ",
            description=OSB_POINTS_TEXT,
            color=discord.Color.dark_grey(),
        )
        await thread.send(embed=help_embed)
    await interaction.followup.send("Рапорт отправлен. Ветка со ссылками создана.", ephemeral=True)
    logger.info("Рапорт ОСБ отправлен: user_id=%s, msg_id=%s", user_id_int, message.id)


class OsbConfirmSubmitView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        yes_btn = discord.ui.Button(label="Да, отправить", style=discord.ButtonStyle.danger, custom_id="osb_confirm_yes")
        yes_btn.callback = self._cb_yes
        no_btn = discord.ui.Button(label="Нет, вернуться", style=discord.ButtonStyle.secondary, custom_id="osb_confirm_no")
        no_btn.callback = self._cb_no
        self.add_item(yes_btn)
        self.add_item(no_btn)

    async def _cb_yes(self, interaction: discord.Interaction):
        if interaction.user and interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
            return
        draft = osb_draft_reports.pop(self.user_id, None)
        if not draft:
            draft = await get_worker().submit(load_osb_draft, self.user_id)
        if not draft:
            await interaction.response.send_message("Сессия истекла. Начните рапорт заново.", ephemeral=True)
            return
        get_worker().submit_fire(delete_osb_draft, self.user_id)
        await interaction.response.defer(ephemeral=True)
        await _do_submit_report(draft, interaction)

    async def _cb_no(self, interaction: discord.Interaction):
        await interaction.response.send_message("Добавьте ещё ссылок и нажмите «Готово» снова.", ephemeral=True)


def _build_remove_link_options(draft: dict, promotion_key: str, max_options: int = 25):
    req_links = draft.get("requirement_links") or {}
    bonus_links = draft.get("bonus_links") or {}
    normalized_bonus = normalize_bonus_links(bonus_links)
    thanks_links = normalize_thanks(draft.get("thanks_links") or [])
    info = PROMOTION_REQUIREMENTS_OSB.get(promotion_key, {})
    req_list = info.get("required", [])
    options = []
    for idx in sort_int_like(req_links.keys()):
        urls = req_links[idx]
        i = int(idx) if str(idx).isdigit() else idx
        short = requirement_short_label(req_list[i - 1], 30) if i <= len(req_list) else ("Пункт %s" % idx)
        for i, u in enumerate(urls):
            if len(options) >= max_options:
                return options
            label = "Обяз. %s: %s…" % (idx, (u[:40] + "…") if len(u) > 40 else u)
            options.append((label[:100], "r_%s_%s" % (idx, i)))
    type_names = {t: n for t, n in OSB_BONUS_LABELS}
    for t in sort_int_like(normalized_bonus.keys()):
        links = normalized_bonus[t]
        tn = type_names.get(int(t) if str(t).isdigit() else t, "Тип %s" % t)
        for i, (url, count) in enumerate(links):
            if len(options) >= max_options:
                return options
            count_str = " x%s" % count if count > 1 else ""
            url_short = (url[:30] + "…") if len(url) > 30 else url
            label = "Баллы %s%s: %s" % (tn[:15], count_str, url_short)
            options.append((label[:100], "b_%s_%s" % (t, i)))
    for i, (p, u) in enumerate(thanks_links):
        if len(options) >= max_options:
            return options
        label = "Благод. %s б.: %s…" % (p, (u[:40] + "…") if len(u) > 40 else u)
        options.append((label[:100], "t_%s" % i))
    return options


class OsbRemoveLinkView(View):
    def __init__(self, owner_id: int, options: list):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        if not options:
            return
        select_opts = [discord.SelectOption(label=l, value=v) for l, v in options]
        sel = discord.ui.Select(placeholder="Выберите ссылку для удаления", min_values=1, max_values=1, options=select_opts, custom_id="osb_remove_sel")
        sel.callback = self._cb_remove
        self.add_item(sel)

    async def _cb_remove(self, interaction: discord.Interaction):
        if not interaction.user:
            return
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
            return
        owner_id = self.owner_id
        vals = interaction.data.get("values", []) if interaction.data else []
        if not vals:
            await interaction.response.send_message("Ничего не выбрано.", ephemeral=True)
            return
        value = vals[0]
        draft = osb_draft_reports.get(owner_id)
        if not draft:
            draft = await get_worker().submit(load_osb_draft, owner_id)
            if draft:
                osb_draft_reports[owner_id] = draft
        if not draft:
            await interaction.response.send_message("Сессия истекла. Нажмите «Продолжить мой рапорт» и попробуйте снова.", ephemeral=True)
            return
        parts = value.split("_")
        if len(parts) < 2:
            await interaction.response.send_message("Ошибка формата.", ephemeral=True)
            return
        try:
            kind = parts[0]
            if kind == "t":
                idx = int(parts[1])
                thanks = normalize_thanks(draft.get("thanks_links") or [])
                if 0 <= idx < len(thanks):
                    thanks.pop(idx)
                    draft["thanks_links"] = thanks
            else:
                if len(parts) != 3:
                    await interaction.response.send_message("Ошибка формата.", ephemeral=True)
                    return
                first, second = int(parts[1]), int(parts[2])
                if kind == "r":
                    req = draft.get("requirement_links") or {}
                    key_r = first if first in req else (str(first) if str(first) in req else None)
                    if key_r is not None and 0 <= second < len(req[key_r]):
                        req[key_r].pop(second)
                        if not req[key_r]:
                            del req[key_r]
                elif kind == "b":
                    bonus = draft.get("bonus_links") or {}
                    key_b = first if first in bonus else (str(first) if str(first) in bonus else None)
                    if key_b is not None and 0 <= second < len(bonus[key_b]):
                        bonus[key_b].pop(second)
                        if not bonus[key_b]:
                            del bonus[key_b]
                else:
                    await interaction.response.send_message("Ошибка формата.", ephemeral=True)
                    return
        except (ValueError, IndexError):
            await interaction.response.send_message("Ошибка формата.", ephemeral=True)
            return
        cid, mid = draft.get("channel_id"), draft.get("message_id")
        ephemeral_msg = draft.get("_ephemeral_msg")
        snapshot = {k: v for k, v in draft.items() if k != "_ephemeral_msg"}
        get_worker().submit_fire(save_osb_draft, owner_id, snapshot)
        if not ephemeral_msg and cid and mid and interaction.guild:
            try:
                ch = None
                cache = getattr(state, "channel_cache", None)
                if cache:
                    ch = await cache.get_channel(cid)
                if ch is None:
                    ch = interaction.guild.get_channel(cid)
                if ch:
                    msg = await ch.fetch_message(mid)
                    await msg.edit(embed=_build_collector_embed(draft))
            except Exception as e:
                logger.warning("Не обновить сообщение после удаления ссылки ОСБ: %s", e)
        embed = _build_collector_embed(draft)
        view = OsbCollectorView(draft.get("promotion_key", ""), owner_id)
        await interaction.response.defer(ephemeral=True)
        content_full = "Ссылка удалена. Ниже — актуальное состояние."
        if interaction.message:
            try:
                await interaction.message.edit(content=content_full, embed=embed, view=view)
            except Exception:
                logger.debug("OsbCollectorView remove link: не удалось отредактировать сообщение, fallback на followup", exc_info=True)
                await interaction.followup.send(content=content_full, embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send("Ссылка удалена. Закройте это уведомление. Состояние обновится при следующем действии в сборщике.", ephemeral=True)


class OsbCollectorView(View):
    def __init__(self, promotion_key: str, owner_id: int):
        super().__init__(timeout=604800)
        self.promotion_key = promotion_key
        self.owner_id = owner_id
        info = PROMOTION_REQUIREMENTS_OSB.get(promotion_key, {})
        req_list = info.get("required", [])
        req_opts = [discord.SelectOption(label=("%s. %s" % (i, requirement_short_label(r, 80))), value=str(i), description="Добавить ссылки") for i, r in enumerate(req_list, start=1)]
        self.req_select = discord.ui.Select(placeholder="Добавить ссылки по требованию", min_values=1, max_values=1, options=req_opts, custom_id="osb_req_sel")
        self.req_select.callback = self._cb_req
        self.add_item(self.req_select)
        bonus_opts = [discord.SelectOption(label="%s. %s" % (t, n), value=str(t)) for t, n in OSB_BONUS_LABELS]
        self.bonus_select = discord.ui.Select(placeholder="Добавить балловые ссылки", min_values=1, max_values=1, options=bonus_opts, custom_id="osb_bonus_sel")
        self.bonus_select.callback = self._cb_bonus
        self.add_item(self.bonus_select)
        bulk_btn = discord.ui.Button(label="Баллы: вставить списком", style=discord.ButtonStyle.primary, custom_id="osb_bonus_bulk")
        bulk_btn.callback = self._cb_bonus_bulk
        self.add_item(bulk_btn)
        done_btn = discord.ui.Button(label="Готово, отправить рапорт", style=discord.ButtonStyle.success, custom_id="osb_done")
        done_btn.callback = self._cb_done
        self.add_item(done_btn)
        thanks_btn = discord.ui.Button(label="Благодарности и поощрения", style=discord.ButtonStyle.secondary, custom_id="osb_thanks")
        thanks_btn.callback = self._cb_thanks
        self.add_item(thanks_btn)
        help_btn = discord.ui.Button(label="Как считаются баллы?", style=discord.ButtonStyle.secondary, custom_id="osb_help_points")
        help_btn.callback = self._cb_help_points
        self.add_item(help_btn)
        remove_btn = discord.ui.Button(label="Удалить ссылку", style=discord.ButtonStyle.danger, custom_id="osb_remove_link")
        remove_btn.callback = self._cb_remove_link
        self.add_item(remove_btn)

    async def _cb_req(self, interaction: discord.Interaction):
        if not interaction.user:
            return
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
            return
        owner_id = interaction.user.id
        draft = osb_draft_reports.get(owner_id)
        if not draft:
            draft = await get_worker().submit(load_osb_draft, owner_id)
            if draft:
                osb_draft_reports[owner_id] = draft
        if not draft:
            await interaction.response.send_message("Черновик не найден. Начните рапорт заново через «Подать рапорт».", ephemeral=True)
            return
        draft["_ephemeral_msg"] = interaction.message
        vals = interaction.data.get("values", []) if interaction.data else []
        idx = int(vals[0]) if vals else 1
        info = PROMOTION_REQUIREMENTS_OSB.get(draft.get("promotion_key", ""), {})
        reqs = info.get("required", [])
        label = reqs[idx - 1] if idx <= len(reqs) else "Требование %s" % idx
        await interaction.response.send_modal(OsbLinksModal(label, requirement_index=idx, bonus_type=None, user_id=interaction.user.id))

    async def _cb_bonus(self, interaction: discord.Interaction):
        if not interaction.user:
            return
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
            return
        owner_id = interaction.user.id
        draft = osb_draft_reports.get(owner_id)
        if not draft:
            draft = await get_worker().submit(load_osb_draft, owner_id)
            if draft:
                osb_draft_reports[owner_id] = draft
        if not draft:
            await interaction.response.send_message("Черновик не найден. Начните рапорт заново через «Подать рапорт».", ephemeral=True)
            return
        draft["_ephemeral_msg"] = interaction.message
        vals = interaction.data.get("values", []) if interaction.data else []
        t = int(vals[0]) if vals else 1
        await interaction.response.send_modal(OsbLinksModal("Баллы: тип %s" % t, requirement_index=None, bonus_type=t, user_id=interaction.user.id))

    async def _cb_bonus_bulk(self, interaction: discord.Interaction):
        if not interaction.user:
            return
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
            return
        owner_id = interaction.user.id
        draft = osb_draft_reports.get(owner_id)
        if not draft:
            draft = await get_worker().submit(load_osb_draft, owner_id)
            if draft:
                osb_draft_reports[owner_id] = draft
        if not draft:
            await interaction.response.send_message("Черновик не найден. Начните рапорт заново через «Подать рапорт».", ephemeral=True)
            return
        draft["_ephemeral_msg"] = interaction.message
        await interaction.response.send_modal(OsbLinksModal(
            "Баллы списком: тип кол-во ссылка",
            requirement_index=None,
            bonus_type=1,
            user_id=interaction.user.id,
            is_bulk=True,
        ))

    async def _cb_help_points(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Как считаются баллы", description="ОСБ", color=discord.Color.blue())
        for name, value in OSB_POINTS_FIELDS:
            embed.add_field(name=name, value=value, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _cb_thanks(self, interaction: discord.Interaction):
        if not interaction.user or interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
            return
        draft = osb_draft_reports.get(self.owner_id)
        if not draft:
            draft = await get_worker().submit(load_osb_draft, self.owner_id)
            if draft:
                osb_draft_reports[self.owner_id] = draft
        if not draft:
            await interaction.response.send_message("Черновик не найден.", ephemeral=True)
            return
        await interaction.response.send_modal(OsbThanksModal(user_id=self.owner_id))

    async def _cb_remove_link(self, interaction: discord.Interaction):
        if not interaction.user:
            return
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
            return
        owner_id = interaction.user.id
        draft = osb_draft_reports.get(owner_id)
        if not draft:
            draft = await get_worker().submit(load_osb_draft, owner_id)
            if draft:
                osb_draft_reports[owner_id] = draft
        if not draft:
            await interaction.response.send_message("Черновик не найден. Начните рапорт заново через «Подать рапорт».", ephemeral=True)
            return
        draft["_ephemeral_msg"] = interaction.message
        options = _build_remove_link_options(draft, draft.get("promotion_key", ""))
        if not options:
            await interaction.response.send_message("Нет добавленных ссылок для удаления.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Выберите ссылку, которую нужно удалить:",
            view=OsbRemoveLinkView(owner_id, options),
            ephemeral=True,
        )

    async def _cb_done(self, interaction: discord.Interaction):
        uid = interaction.user.id if interaction.user else 0
        if not uid:
            return
        if uid != self.owner_id:
            await interaction.response.send_message("❌ Это не ваш черновик.", ephemeral=True)
            return
        draft = osb_draft_reports.get(uid)
        if not draft:
            draft = await get_worker().submit(load_osb_draft, uid)
            if draft:
                osb_draft_reports[uid] = draft
        if not draft:
            await interaction.response.send_message("Черновик не найден. Начните заново через «Подать рапорт».", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        info = PROMOTION_REQUIREMENTS_OSB.get(draft.get("promotion_key", ""), {})
        required_list = info.get("required", [])
        points_required = info.get("points", 0)
        req_links = draft.get("requirement_links") or {}
        bonus_links = draft.get("bonus_links") or {}
        fulfilled = 0
        for idx, req in enumerate(required_list, start=1):
            if len(req_links.get(idx, [])) >= required_count_from_text(req):
                fulfilled += 1
        total_bonus = calc_bonus_points(bonus_links, OSB_POINTS_MAP)
        thanks = normalize_thanks(draft.get("thanks_links") or [])
        total_bonus += sum(p for p, u in thanks)
        req_ok = fulfilled >= len(required_list) if required_list else True
        points_ok = total_bonus >= points_required
        if req_ok and points_ok:
            osb_draft_reports.pop(uid, None)
            get_worker().submit_fire(delete_osb_draft, uid)
            await _do_submit_report(draft, interaction)
        else:
            missing = []
            if not req_ok:
                missing.append("обязательные %s/%s" % (fulfilled, len(required_list)))
            if not points_ok:
                missing.append("баллов %s/%s" % (total_bonus, points_required))
            await interaction.followup.send(
                "Не выполнено: " + ", ".join(missing) + ". Всё равно отправить?",
                view=OsbConfirmSubmitView(uid),
                ephemeral=True,
            )


class OsbPromotionModal(discord.ui.Modal, title="Рапорт на повышение ОСБ"):
    def __init__(self, promotion_key: str, user_id: int | None = None):
        super().__init__(timeout=None)
        self.promotion_key = promotion_key
        last = osb_last_user_data.get(user_id or 0) or {}
        discord_default = str(user_id) if user_id else ""
        self.full_name = discord.ui.TextInput(
            label="Имя Фамилия",
            max_length=Config.MAX_NAME_LENGTH,
            required=True,
            default=last.get("full_name", "")[:Config.MAX_NAME_LENGTH],
        )
        self.discord_id = discord.ui.TextInput(
            label="Discord ID",
            max_length=32,
            required=True,
            placeholder="Числовой ID",
            default=last.get("discord_id") or discord_default,
        )
        self.passport = discord.ui.TextInput(
            label="Номер паспорта",
            max_length=Config.STATIC_ID_LENGTH,
            required=True,
            default=last.get("passport", "")[:Config.STATIC_ID_LENGTH],
        )
        self.add_item(self.full_name)
        self.add_item(self.discord_id)
        self.add_item(self.passport)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            if isinstance(interaction.user, discord.Member) and interaction.guild:
                dept_role_id = get_dept_role_id("osb")
                role = None
                role_cache = getattr(state, "role_cache", None)
                if role_cache and dept_role_id:
                    role = await role_cache.get_role(interaction.guild.id, dept_role_id)
                if role is None and dept_role_id:
                    role = interaction.guild.get_role(dept_role_id) if interaction.guild else None
                if role and role not in interaction.user.roles:
                    await interaction.response.send_message(
                        "❌ Подать рапорт на повышение ОСБ может только сотрудник отдела ОСБ.",
                        ephemeral=True,
                    )
                    return
            if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message("Рапорт можно подать только в текстовом канале.", ephemeral=True)
                return
            if isinstance(Config.PROMOTION_CHANNELS, dict) and interaction.channel.id not in Config.PROMOTION_CHANNELS:
                await interaction.response.send_message("Этот канал не для рапортов ОСБ.", ephemeral=True)
                return
            try:
                user_id = int(str(self.discord_id.value).strip())
            except ValueError:
                await interaction.response.send_message("Некорректный Discord ID.", ephemeral=True)
                return
            draft = {
                "channel_id": interaction.channel.id,
                "promotion_key": self.promotion_key,
                "full_name": self.full_name.value.strip(),
                "discord_id": str(user_id),
                "passport": self.passport.value.strip(),
                "requirement_links": {},
                "bonus_links": {},
                "thanks_links": [],
            }
            collector_embed = _build_collector_embed(draft)
            collector_view = OsbCollectorView(self.promotion_key, interaction.user.id)
            await interaction.response.send_message(
                content="Данные приняты. Добавляйте ссылки и нажмите «Готово, отправить рапорт».",
                embed=collector_embed,
                view=collector_view,
                ephemeral=True,
            )
            draft["message_id"] = None
            draft["channel_id"] = interaction.channel.id
            osb_draft_reports[interaction.user.id] = draft
            snapshot = {k: v for k, v in draft.items() if k != "_ephemeral_msg"}
            get_worker().submit_fire(save_osb_draft, interaction.user.id, snapshot)
            osb_last_user_data[interaction.user.id] = {
                "full_name": draft["full_name"],
                "discord_id": draft["discord_id"],
                "passport": draft["passport"],
            }
        except Exception as e:
            logger.error("Ошибка OsbPromotionModal: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, "Ошибка при отправке.", ephemeral=True)


class OsbPromotionSelect(Select):
    def __init__(self):
        options = [discord.SelectOption(label=key, value=key, description="Баллы: %s" % info["points"]) for key, info in PROMOTION_REQUIREMENTS_OSB.items()]
        super().__init__(placeholder="Выберите повышение ОСБ", min_values=1, max_values=1, options=options, custom_id="osb_promotion_select")

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            if isinstance(interaction.user, discord.Member) and interaction.guild:
                dept_role_id = get_dept_role_id("osb")
                role = None
                role_cache = getattr(state, "role_cache", None)
                if role_cache and dept_role_id:
                    role = await role_cache.get_role(interaction.guild.id, dept_role_id)
                if role is None and dept_role_id:
                    role = interaction.guild.get_role(dept_role_id) if interaction.guild else None
                if role and role not in interaction.user.roles:
                    await interaction.response.send_message(
                        "❌ Подать рапорт на повышение ОСБ может только сотрудник отдела ОСБ.",
                        ephemeral=True,
                    )
                    return
            promotion_key = self.values[0]
            if not is_promotion_key_allowed_for_member(interaction.user, promotion_key):
                current = get_member_rank_display(interaction.user) or "не определено"
                await interaction.response.send_message(
                    "Рапорт можно подать только на следующее звание. Ваше текущее звание: **%s**. Выберите повышение, соответствующее вашему званию." % current,
                    ephemeral=True,
                )
                return
            user_id = interaction.user.id if interaction.user else None
            if user_id:
                await drop_orphan_promotion_requests_for_user(user_id, interaction.client)
            if user_id and await has_active_promotion(user_id):
                await interaction.response.send_message(
                    "❌ У вас уже есть активный рапорт на повышение. Дождитесь решения по текущему рапорту.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_modal(OsbPromotionModal(promotion_key=promotion_key, user_id=user_id))
        except Exception as e:
            logger.error("Ошибка открытия модала ОСБ: %s", e, exc_info=True)
            await safe_followup_or_response(interaction, "Ошибка.", ephemeral=True)


class OsbPromotionApplyView(View):
    timeout = None

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(OsbPromotionSelect())
        resume_btn = discord.ui.Button(label="Продолжить мой рапорт", style=discord.ButtonStyle.secondary, custom_id="osb_resume_draft")
        resume_btn.callback = self._cb_resume_draft
        self.add_item(resume_btn)

    async def _cb_resume_draft(self, interaction: discord.Interaction):
        if not interaction.user:
            return
        if isinstance(interaction.user, discord.Member) and interaction.guild:
            dept_role_id = get_dept_role_id("osb")
            role = None
            role_cache = getattr(state, "role_cache", None)
            if role_cache and dept_role_id:
                role = await role_cache.get_role(interaction.guild.id, dept_role_id)
            if role is None and dept_role_id:
                role = interaction.guild.get_role(dept_role_id)
            if role and role not in interaction.user.roles:
                await interaction.response.send_message(
                    "❌ Продолжить рапорт ОСБ может только сотрудник отдела ОСБ.",
                    ephemeral=True,
                )
                return
        uid = interaction.user.id
        draft = osb_draft_reports.get(uid)
        if not draft:
            draft = await get_worker().submit(load_osb_draft, uid)
        if not draft:
            await drop_orphan_promotion_requests_for_user(uid, interaction.client)
            if await has_active_promotion(uid):
                await interaction.response.send_message(
                    "✅ Ваш рапорт уже отправлен и ожидает проверки. Дождитесь решения по нему.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message("У вас нет черновика рапорта ОСБ. Выберите повышение выше, чтобы начать новый рапорт.", ephemeral=True)
            return
        osb_draft_reports[uid] = draft
        promotion_key = draft.get("promotion_key", "")
        collector_embed = _build_collector_embed(draft)
        collector_view = OsbCollectorView(promotion_key, uid)
        await interaction.response.send_message(embed=collector_embed, view=collector_view, ephemeral=True)
