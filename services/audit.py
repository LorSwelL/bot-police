import aiohttp
import asyncio
import logging
import re

from config import Config

logger = logging.getLogger(__name__)


_AUDIT_RANK_LABELS = {
    "рядовой": "Рядовой полиции",
    "рядовой полиции": "Рядовой полиции",
    "младший сержант": "Младший сержант полиции",
    "младший сержант полиции": "Младший сержант полиции",
    "сержант": "Сержант полиции",
    "сержант полиции": "Сержант полиции",
    "старший сержант": "Старший сержант полиции",
    "старший сержант полиции": "Старший сержант полиции",
    "старшина": "Старшина полиции",
    "старшина полиции": "Старшина полиции",
    "прапорщик": "Прапорщик полиции",
    "прапорщик полиции": "Прапорщик полиции",
    "старший прапорщик": "Старший прапорщик полиции",
    "старший прапорщик полиции": "Старший прапорщик полиции",
    "младший лейтенант": "Младший лейтенант полиции",
    "младший лейтенант полиции": "Младший лейтенант полиции",
    "лейтенант": "Лейтенант полиции",
    "лейтенант полиции": "Лейтенант полиции",
    "старший лейтенант": "Старший лейтенант полиции",
    "старший лейтенант полиции": "Старший лейтенант полиции",
    "капитан": "Капитан полиции",
    "капитан полиции": "Капитан полиции",
    "майор": "Майор полиции",
    "майор полиции": "Майор полиции",
    "подполковник": "Подполковник полиции",
    "подполковник полиции": "Подполковник полиции",
    "полковник": "Полковник полиции",
    "полковник полиции": "Полковник полиции",
    "уволен": "УВОЛЕН",
    "уволен с чс": "УВОЛЕН С ЧС",
}

_ARROW_RE = re.compile(r"\s*(?:->|→|➡|⇒|=+>)\s*", re.IGNORECASE)


def _clean_rank_text(rank: str) -> str:
    if not rank:
        return ""

    text = str(rank).strip()


    parts = _ARROW_RE.split(text)
    if len(parts) == 2:
        text = parts[1].strip()

    text = " ".join(text.lower().split())
    text = text.replace("ё", "е")
    return text


def _get_rank_value(action: str, rank: str) -> str:
    if action == Config.ACTION_FIRED:
        return "УВОЛЕН"

    if action == Config.ACTION_ACCEPTED:
        return "Рядовой полиции"

    if action == Config.ACTION_PROMOTED:
        cleaned = _clean_rank_text(rank)
        mapped = _AUDIT_RANK_LABELS.get(cleaned)
        if mapped:
            return mapped


        if cleaned in {"уволен", "уволен с чс"}:
            return _AUDIT_RANK_LABELS[cleaned]

        title = " ".join(word.capitalize() for word in cleaned.split())
        if title:
            return f"{title} полиции"

        return str(rank)

    return str(rank)


def _build_form_data(interaction, target_member, action, rank_value, reason_link: str) -> dict:

    return {
        Config.AUDIT_FIELD_OFFICER: str(interaction.user.id),
        Config.AUDIT_FIELD_TARGET_ID: str(target_member.id),
        Config.AUDIT_FIELD_ACTION: action,
        Config.AUDIT_FIELD_RANK: rank_value,
        Config.AUDIT_FIELD_REASON_LINK: reason_link,
    }


async def _safe_followup_warning(interaction, text: str):
    try:
        await interaction.followup.send(text, ephemeral=True)
    except Exception as e:
        logger.warning("Аудит: не удалось отправить followup-предупреждение: %s", e, exc_info=True)


async def send_to_audit(interaction, target_member, action, rank, reason_link):
    rank_value = _get_rank_value(action, rank)


    if not Config.AUDIT_FORM_URL:
        logger.warning("Аудит: AUDIT_FORM_URL не настроен, отправка в форму пропущена")
        await _safe_followup_warning(
            interaction,
            "⚠️ Внешний кадровый аудит не настроен (AUDIT_FORM_URL). Действие выполнено без отправки в форму."
        )
        return False

    form_data = _build_form_data(interaction, target_member, action, rank_value, reason_link)

    logger.info(
        "Аудит: отправка action=%s officer=%s target=%s rank=%s",
        action,
        interaction.user.id,
        target_member.id,
        rank_value,
    )

    try:
        timeout = aiohttp.ClientTimeout(total=20)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                Config.AUDIT_FORM_URL,
                data=form_data,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
            ) as resp:
                status = resp.status
                logger.info("Аудит: ответ Google Forms status=%s", status)

                if status in (200, 204, 302, 303):
                    return True

                try:
                    text = await resp.text()
                    logger.warning("Аудит: неожиданный статус=%s, ответ=%s", status, text[:200])
                except Exception:
                    logger.warning("Аудит: неожиданный статус=%s, тело ответа не прочитано", status)

                await _safe_followup_warning(
                    interaction,
                    "⚠️ Не удалось отправить данные в кадровый аудит, но действие выполнено."
                )
                return False

    except asyncio.TimeoutError:
        logger.warning("Аудит: таймаут отправки")
        await _safe_followup_warning(
            interaction,
            "⚠️ Таймаут отправки в кадровый аудит, но действие выполнено."
        )
        return False

    except Exception as e:
        logger.error("Аудит: ошибка отправки: %s", e, exc_info=True)
        await _safe_followup_warning(
            interaction,
            "⚠️ Ошибка отправки в кадровый аудит, но действие выполнено."
        )
        return False