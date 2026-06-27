import logging
from typing import Any, Iterable, Mapping

import discord

from config import Config
from utils.promotion_helpers import (
    links_word,
    normalize_thanks,
    normalize_bonus_links,
    calc_bonus_points,
    required_count_from_text,
    requirement_short_label,
)


logger = logging.getLogger(__name__)


def get_reviewers_mention_content(channel_id: int) -> str:
    """
    Возвращает строку с упоминаниями ролей, имеющих право проверять рапорты в данном канале
    (одобрять/отклонять). Формат: "На рассмотрение: <@&id1> <@&id2>".
    """
    role_ids = list(Config.PROMOTION_CHANNELS.get(channel_id, []) or [])
    if not role_ids:
        return ""
    mentions = " ".join("<@&%s>" % int(rid) for rid in role_ids if rid)
    if not mentions:
        return ""
    return "На рассмотрение: " + mentions


def sort_int_like(keys: Iterable[Any]) -> list[Any]:
    """Стабильно сортирует ключи, где возможны строковые/числовые номера."""
    return sorted(keys, key=lambda k: int(k) if str(k).isdigit() else -1)


async def has_active_promotion(user_id: int) -> bool:
    """
    Проверка наличия активного рапорта на повышение для пользователя.

    Предпочитает слой Store (PromotionRequestStore), при недоступности или
    ошибке падает обратно на in‑memory словарь state.active_promotion_requests.
    """
    try:
        import state  # type: ignore
    except Exception:
        logger.warning("has_active_promotion: модуль state недоступен")
        return False

    try:
        promo_store = getattr(state, "promotion_store", None)
    except Exception as e:
        logger.warning("has_active_promotion: не удалось получить promotion_store: %s", e, exc_info=True)
        promo_store = None

    user_id = int(user_id)

    if promo_store is not None:
        try:
            return await promo_store.has_active_for_user(user_id)
        except Exception as e:
            logger.warning(
                "has_active_promotion: ошибка Store.has_active_for_user user_id=%s: %s",
                user_id,
                e,
                exc_info=True,
            )

    try:
        from state import active_promotion_requests  # type: ignore
    except Exception:
        logger.debug("has_active_promotion: не удалось импортировать active_promotion_requests", exc_info=True)
        active_promotion_requests = getattr(state, "active_promotion_requests", {}) or {}

    return any(
        (data or {}).get("discord_id") == user_id
        for data in (active_promotion_requests or {}).values()
    )


async def drop_orphan_promotion_requests_for_user(user_id: int, bot) -> None:
    """
    Удаляет записи о рапортах пользователя, для которых сообщение в Discord уже не существует
    (удалено, канал удалён и т.д.). Разблокирует пользователя, если рапорт был «потерян».
    """
    try:
        import state  # type: ignore
    except Exception:
        return
    user_id = int(user_id)
    promo_store = getattr(state, "promotion_store", None)
    storage = getattr(state, "active_promotion_requests", None) or {}
    to_remove = [
        (int(msg_id), data)
        for msg_id, data in (storage or {}).items()
        if (data or {}).get("discord_id") == user_id
    ]
    if not to_remove:
        return
    channel_ids = list((Config.PROMOTION_CHANNELS or {}).keys())
    for msg_id, _ in to_remove:
        found = False
        tried_any = False
        for ch_id in channel_ids:
            try:
                ch = bot.get_channel(int(ch_id))
                if ch is None and hasattr(bot, "fetch_channel"):
                    try:
                        ch = await bot.fetch_channel(int(ch_id))
                    except Exception:
                        ch = None
                if not ch or not hasattr(ch, "fetch_message"):
                    continue
                tried_any = True
                await ch.fetch_message(msg_id)
                found = True
                break
            except discord.NotFound:
                continue
            except Exception as e:
                logger.debug("drop_orphan_promotion: fetch_message msg_id=%s ch_id=%s: %s", msg_id, ch_id, e)
                continue
        if tried_any and not found:
            try:
                if promo_store is not None:
                    await promo_store.remove_active(msg_id)
                else:
                    from database import delete_request
                    await delete_request("promotion_requests", msg_id)
                    storage.pop(msg_id, None)
                logger.info(
                    "🧹 Удалена осиротевшая запись повышения для user_id=%s msg_id=%s (сообщение не найдено)",
                    user_id,
                    msg_id,
                )
            except Exception as e:
                logger.warning(
                    "Не удалось удалить осиротевшую запись повышения msg_id=%s: %s",
                    msg_id,
                    e,
                    exc_info=True,
                )


def build_generic_collector_embed(
    draft: Mapping[str, Any],
    promotion_requirements: Mapping[str, Mapping[str, Any]],
    points_map: Mapping[Any, int],
    department_label: str,
) -> discord.Embed:
    """
    Общий расчёт и отображение прогресса по обязательным требованиям и баллам.

    Используется ОСБ/ГРОМ/ППС; ОРЛС при необходимости может остаться на своём
    более специфичном расчёте.
    """
    promotion_key = draft.get("promotion_key", "")
    full_name = draft.get("full_name", "")
    req_links = draft.get("requirement_links") or {}
    bonus_links = draft.get("bonus_links") or {}
    info = promotion_requirements.get(promotion_key, {}) or {}
    required_list = info.get("required", []) or []
    points_required = int(info.get("points") or 0)

    fulfilled = 0
    for idx, req in enumerate(required_list, start=1):
        need = required_count_from_text(req)
        if len(req_links.get(idx, [])) >= need:
            fulfilled += 1

    normalized_bonus = normalize_bonus_links(bonus_links)
    total_bonus = calc_bonus_points(bonus_links, points_map)

    thanks = normalize_thanks(draft.get("thanks_links") or [])
    total_bonus += sum(p for p, _ in thanks)

    req_ok = fulfilled >= len(required_list) if required_list else True
    points_ok = total_bonus >= points_required
    can_submit = req_ok and points_ok

    if can_submit:
        color = discord.Color.green()
    elif fulfilled > 0 or total_bonus > 0:
        color = discord.Color.gold()
    else:
        color = discord.Color.from_rgb(128, 128, 128)

    points_bar_len = 10
    if points_required > 0:
        pct = min(100, int(100 * total_bonus / max(points_required, 1)))
        filled = int(points_bar_len * min(1.0, total_bonus / max(points_required, 1)))
        bar = "█" * filled + "░" * (points_bar_len - filled)
        points_progress = "[%s] %s/%s б. (%s%%)" % (bar, total_bonus, points_required, pct)
    else:
        points_progress = "%s б." % total_bonus
    bonus_status = "✓ хватает" if points_ok else "✗ ещё %s б." % max(points_required - total_bonus, 0)

    summary_parts: list[str] = []
    summary_parts.append("Обязательные: **%s/%s** %s" % (fulfilled, len(required_list), "✓" if req_ok else "✗"))
    summary_parts.append("Баллы: **%s** %s" % (points_progress, "✓" if points_ok else "✗"))
    summary_parts.append("**Можно отправлять**" if can_submit else "Пока не готово")
    one_line = " · ".join(summary_parts)

    embed = discord.Embed(
        title="Добавьте ссылки по требованиям (%s)" % department_label,
        description="**%s** · %s\n\n%s\n\nВыберите требование или тип баллов и добавьте ссылки."
        % (full_name, promotion_key, one_line),
        color=color,
    )
    embed.add_field(
        name="Баллы (автоподсчёт)",
        value="Нужно для звания: **%s** б. · Сейчас: **%s** б. · %s"
        % (points_required, total_bonus, bonus_status),
        inline=False,
    )

    lines: list[str] = []
    for idx, req in enumerate(required_list, start=1):
        need = required_count_from_text(req)
        count = len(req_links.get(idx, []))
        ok = "✓" if count >= need else "✗ (нужно %s)" % need
        short = requirement_short_label(req, 40)
        lines.append("**%s. %s** — %s %s %s" % (idx, short, count, links_word(count), ok))
    if lines:
        embed.add_field(name="Обязательные", value="\n".join(lines), inline=False)

    bonus_parts: list[str] = []
    for t in sort_int_like(normalized_bonus.keys()):
        links = normalized_bonus[t]
        try:
            key = int(t) if str(t).isdigit() else t
        except Exception:
            key = t
        pts_per_item = int(points_map.get(key, 0))
        total_items = sum(count for url, count in links)
        pts = pts_per_item * total_items
        bonus_parts.append("Тип %s: %s фикс. (%s ссыл.) = %s б." % (t, total_items, len(links), pts))
    if bonus_parts:
        embed.add_field(
            name="Балловые",
            value="\n".join(bonus_parts) + "\n**Итого: %s б.**" % total_bonus,
            inline=False,
        )

    if thanks:
        thanks_parts = ["%s б.: %s" % (p, u) for p, u in thanks]
        embed.add_field(
            name="Благодарности и поощрения",
            value="\n".join(thanks_parts) + "\n**Всего: %s б.**" % sum(p for p, _ in thanks),
            inline=False,
        )

    embed.set_footer(
        text="Когда всё добавлено — нажмите «Готово, отправить рапорт». Справка: кнопка «Как считаются баллы?»"
    )
    return embed

