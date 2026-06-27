import logging
from typing import Iterable

import discord

from config import Config
import state

logger = logging.getLogger(__name__)


def _ok(text: str) -> str:
    return f"✅ {text}"


def _warn(text: str) -> str:
    return f"⚠️ {text}"


def _err(text: str) -> str:
    return f"❌ {text}"


async def _check_channel(guild: discord.Guild, channel_id: int, name: str) -> bool:
    if not channel_id:
        logger.error(_err(f"{name}: ID не задан в config/.env"))
        return False

    ch = None
    cache = getattr(state, "channel_cache", None)
    if cache is not None:
        ch = await cache.get_channel(channel_id)
    if ch is None:
        ch = guild.get_channel(channel_id)
    if ch is None:
        logger.error(_err(f"{name}: канал не найден (ID={channel_id})"))
        return False

    me = guild.me or guild.get_member(guild._state.user.id)
    if me is None:
        logger.error(_err(f"{name}: не удалось получить участника бота на сервере (ID={channel_id})"))
        return False

    perms = ch.permissions_for(me)

    required = {
        "просмотр_канала": perms.view_channel,
        "отправка_сообщений": getattr(perms, "send_messages", True),
        "чтение_истории": perms.read_message_history,
    }

    missing = [perm_name for perm_name, ok in required.items() if not ok]
    if missing:
        logger.warning(_warn(f"{name}: канал найден, но не хватает прав {missing} (ID={channel_id})"))
    else:
        logger.info(_ok(f"{name}: канал найден и доступен (ID={channel_id})"))
    return True


def _check_role(guild: discord.Guild, role_id: int, name: str, bot_role: discord.Role | None = None) -> bool:
    if not role_id:
        logger.error(_err(f"{name}: ID не задан в config/.env"))
        return False

    role = guild.get_role(role_id)
    if role is None:
        logger.error(_err(f"{name}: роль не найдена (ID={role_id})"))
        return False

    if bot_role and role >= bot_role:
        logger.warning(
            _warn(
                f"{name}: роль найдена, но она выше/равна роли бота "
                f"('{role.name}' >= '{bot_role.name}'). Бот не сможет её выдать/снять."
            )
        )
    else:
        logger.info(_ok(f"{name}: роль найдена (ID={role_id}, name='{role.name}')"))
    return True


def _check_role_list(guild: discord.Guild, role_ids: Iterable[int], name: str, bot_role: discord.Role | None = None):
    ids = [int(x) for x in (role_ids or []) if x]
    if not ids:
        logger.warning(_warn(f"{name}: список пустой"))
        return

    for rid in ids:
        _check_role(guild, rid, f"{name} -> {rid}", bot_role=bot_role)


async def _check_promotion_channels(guild: discord.Guild):
    mapping = getattr(Config, "PROMOTION_CHANNELS", {}) or {}
    if not mapping:
        logger.warning(_warn("PROMOTION_CHANNELS: список пуст"))
        return
    for channel_id, role_ids in mapping.items():
        await _check_channel(guild, int(channel_id), f"Канал повышений {channel_id}")

        for rid in (role_ids or []):
            _check_role(guild, int(rid), f"Роль кадровика для канала повышений {channel_id}")


def _check_rank_roles(guild: discord.Guild, bot_role: discord.Role | None):
    _check_role_list(guild, getattr(Config, "ALL_RANK_ROLE_IDS", []), "ALL_RANK_ROLE_IDS", bot_role=bot_role)

    mapping = getattr(Config, "RANK_ROLE_MAPPING", {}) or {}
    seen = set()

    for transition, role_id in mapping.items():
        try:
            rid = int(role_id)
        except Exception:
            logger.error(_err(f"RANK_ROLE_MAPPING: неверный role_id для '{transition}' -> {role_id}"))
            continue

        if rid in seen:
            continue
        seen.add(rid)

        role = guild.get_role(rid)
        if role is None:
            logger.error(_err(f"RANK_ROLE_MAPPING: роль не найдена для '{transition}' (ID={rid})"))
            continue

        if bot_role and role >= bot_role:
            logger.warning(
                _warn(
                    f"RANK_ROLE_MAPPING: роль '{role.name}' (ID={rid}) выше/равна роли бота. "
                    f"Повышение/снятие званий может не работать."
                )
            )
        else:
            logger.info(_ok(f"RANK_ROLE_MAPPING: '{transition}' -> '{role.name}' (ID={rid})"))


async def run_startup_checks(bot: discord.Client):
    logger.info("========== ПРОВЕРКА ПРИ ЗАПУСКЕ ==========")

    guild = bot.get_guild(Config.GUILD_ID)
    if guild is None:
        logger.error(_err(f"GUILD_ID={Config.GUILD_ID} не найден. Проверь .env"))
        logger.info("==========================================")
        return

    me = guild.me or guild.get_member(bot.user.id)
    if me is None:
        logger.error(_err("Не удалось получить участника бота на сервере"))
        logger.info("==========================================")
        return

    bot_role = me.top_role
    logger.info(_ok(f"Сервер: {guild.name} (ID={guild.id})"))
    logger.info(_ok(f"Бот: {me} | верхняя роль='{bot_role.name}' | позиция={bot_role.position}"))

    await _check_channel(guild, getattr(Config, "START_CHANNEL_ID", 0), "START_CHANNEL_ID")
    await _check_channel(guild, getattr(Config, "REQUEST_CHANNEL_ID", 0), "REQUEST_CHANNEL_ID")
    await _check_channel(guild, getattr(Config, "FIRING_CHANNEL_ID", 0), "FIRING_CHANNEL_ID")
    await _check_channel(guild, getattr(Config, "WAREHOUSE_REQUEST_CHANNEL_ID", 0), "WAREHOUSE_REQUEST_CHANNEL_ID")
    await _check_channel(guild, getattr(Config, "WAREHOUSE_AUDIT_CHANNEL_ID", 0), "WAREHOUSE_AUDIT_CHANNEL_ID")
    await _check_channel(guild, getattr(Config, "ACADEMY_CHANNEL_ID", 0), "ACADEMY_CHANNEL_ID")
    await _check_channel(guild, getattr(Config, "EXAM_CHANNEL_ID", 0), "EXAM_CHANNEL_ID")

    if getattr(Config, "CHANNEL_APPLY_GROM", 0):
        await _check_channel(guild, Config.CHANNEL_APPLY_GROM, "CHANNEL_APPLY_GROM")
    if getattr(Config, "CHANNEL_APPLY_PPS", 0):
        await _check_channel(guild, Config.CHANNEL_APPLY_PPS, "CHANNEL_APPLY_PPS")
    if getattr(Config, "CHANNEL_APPLY_OSB", 0):
        await _check_channel(guild, Config.CHANNEL_APPLY_OSB, "CHANNEL_APPLY_OSB")
    if getattr(Config, "CHANNEL_APPLY_ORLS", 0):
        await _check_channel(guild, Config.CHANNEL_APPLY_ORLS, "CHANNEL_APPLY_ORLS")
    if getattr(Config, "CHANNEL_ADMIN_TRANSFER", 0):
        await _check_channel(guild, Config.CHANNEL_ADMIN_TRANSFER, "CHANNEL_ADMIN_TRANSFER")
    if getattr(Config, "CHANNEL_CADRE_LOG", 0):
        await _check_channel(guild, Config.CHANNEL_CADRE_LOG, "CHANNEL_CADRE_LOG")

    _check_role(guild, getattr(Config, "STAFF_ROLE_ID", 0), "STAFF_ROLE_ID", bot_role=bot_role)
    _check_role(guild, getattr(Config, "TRANSFER_STAFF_ROLE_ID", 0), "TRANSFER_STAFF_ROLE_ID", bot_role=bot_role)
    _check_role(guild, getattr(Config, "GOV_STAFF_ROLE_ID", 0), "GOV_STAFF_ROLE_ID", bot_role=bot_role)
    _check_role(guild, getattr(Config, "FIRING_STAFF_ROLE_ID", 0), "FIRING_STAFF_ROLE_ID", bot_role=bot_role)
    _check_role(guild, getattr(Config, "FIRING_SENIOR_ROLE_ID", 0), "FIRING_SENIOR_ROLE_ID", bot_role=bot_role)
    _check_role(guild, getattr(Config, "WAREHOUSE_STAFF_ROLE_ID", 0), "WAREHOUSE_STAFF_ROLE_ID", bot_role=bot_role)

    _check_role(guild, getattr(Config, "FIRED_ROLE_ID", 0), "FIRED_ROLE_ID", bot_role=bot_role)
    _check_role_list(guild, getattr(Config, "ROLES_TO_KEEP_ON_FIRE", []), "ROLES_TO_KEEP_ON_FIRE", bot_role=bot_role)
    _check_role_list(guild, getattr(Config, "CADET_ROLES_TO_GIVE", []), "CADET_ROLES_TO_GIVE", bot_role=bot_role)
    _check_role_list(guild, getattr(Config, "TRANSFER_ROLES_TO_GIVE", []), "TRANSFER_ROLES_TO_GIVE", bot_role=bot_role)
    _check_role(guild, getattr(Config, "GOV_ROLE_TO_GIVE", 0), "GOV_ROLE_TO_GIVE", bot_role=bot_role)
    _check_role_list(guild, getattr(Config, "PPS_ROLE_IDS", []), "PPS_ROLE_IDS", bot_role=bot_role)

    for name in ("ROLE_CHIEF_GROM", "ROLE_DEPUTY_GROM", "ROLE_CHIEF_PPS", "ROLE_DEPUTY_PPS",
                 "ROLE_CHIEF_OSB", "ROLE_DEPUTY_OSB", "ROLE_CHIEF_ORLS", "ROLE_DEPUTY_ORLS"):
        rid = getattr(Config, name, 0)
        if rid:
            _check_role(guild, rid, name, bot_role=bot_role)
    for name in ("ROLE_DEPT_GROM", "ROLE_DEPT_PPS", "ROLE_DEPT_OSB", "ROLE_DEPT_ORLS"):
        rid = getattr(Config, name, 0)
        if rid:
            _check_role(guild, rid, name, bot_role=bot_role)
    for list_name in ("ROLE_RANK_GROM", "ROLE_RANK_PPS", "ROLE_RANK_OSB", "ROLE_RANK_ORLS"):
        ids = getattr(Config, list_name, None) or []
        if ids:
            _check_role_list(guild, ids, list_name, bot_role=bot_role)
    if getattr(Config, "ROLE_ACADEMY", 0):
        _check_role(guild, Config.ROLE_ACADEMY, "ROLE_ACADEMY", bot_role=bot_role)
    if getattr(Config, "ROLE_DEPT_ACADEMY", 0):
        _check_role(guild, Config.ROLE_DEPT_ACADEMY, "ROLE_DEPT_ACADEMY", bot_role=bot_role)
    rank_academy = getattr(Config, "ROLE_RANK_ACADEMY", None) or []
    if rank_academy:
        _check_role_list(guild, rank_academy, "ROLE_RANK_ACADEMY", bot_role=bot_role)
    if getattr(Config, "ROLE_PASSED_ACADEMY", 0):
        _check_role(guild, Config.ROLE_PASSED_ACADEMY, "ROLE_PASSED_ACADEMY", bot_role=bot_role)

    await _check_promotion_channels(guild)
    _check_rank_roles(guild, bot_role)

    for name, ch_id in (
        ("Канал рапортов ОРЛС", getattr(Config, "PROMOTION_APPLY_CHANNEL_ORLS", 0)),
        ("Канал рапортов ОСБ", getattr(Config, "PROMOTION_APPLY_CHANNEL_OSB", 0)),
        ("Канал рапортов ГРОМ", getattr(Config, "PROMOTION_APPLY_CHANNEL_GROM", 0)),
        ("Канал рапортов ППС", getattr(Config, "PROMOTION_APPLY_CHANNEL_PPS", 0)),
    ):
        if ch_id:
            await _check_channel(guild, ch_id, name)

    guild_perms = me.guild_permissions
    if not guild_perms.manage_roles:
        logger.error(_err("У бота нет права 'Управлять ролями'"))
    else:
        logger.info(_ok("У бота есть право 'Управлять ролями'"))

    if not guild_perms.manage_nicknames:
        logger.warning(_warn("У бота нет права 'Управлять никами' (смена ников может не работать)"))
    else:
        logger.info(_ok("У бота есть право 'Управлять никами'"))

    logger.info("======== ПРОВЕРКА ПРИ ЗАПУСКЕ ЗАВЕРШЕНА ========")