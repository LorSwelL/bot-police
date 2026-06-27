import logging
import asyncio
import discord

import state
from config import Config
from database import (
    load_all_requests,
    load_all_firing_requests,
    load_all_promotion_requests,
    load_all_warehouse_requests,
    load_all_department_transfer_requests,
    delete_request,
    delete_department_transfer_request,
)

logger = logging.getLogger(__name__)


def log_memory_state():
    try:
        orls_d = len(getattr(state, "orls_draft_reports", {}) or {})
        osb_d = len(getattr(state, "osb_draft_reports", {}) or {})
        grom_d = len(getattr(state, "grom_draft_reports", {}) or {})
        pps_d = len(getattr(state, "pps_draft_reports", {}) or {})
        academy_d = len(getattr(state, "academy_draft_reports", {}) or {})
        promo_setup = sum(len(v) for v in (getattr(state, "promotion_setup_messages", {}) or {}).values())
        logger.info(
            "📊 ПАМЯТЬ | заявки=%s | увольнения=%s | повышения=%s | склад=%s | переводы=%s | черновики_ОРЛС=%s ОСБ=%s ГРОМ=%s ППС=%s Акад=%s | сообщ_рапортов=%s",
            len(getattr(state, "active_requests", {}) or {}),
            len(getattr(state, "active_firing_requests", {}) or {}),
            len(getattr(state, "active_promotion_requests", {}) or {}),
            len(getattr(state, "warehouse_requests", {}) or {}),
            len(getattr(state, "active_department_transfers", {}) or {}),
            orls_d, osb_d, grom_d, pps_d, academy_d,
            promo_setup,
        )
    except Exception as e:
        logger.error("Отчёт состояния: ошибка чтения памяти (state): %s", e, exc_info=True)


async def _load_all_tables_for_report():
    req = await load_all_requests()
    fir = await load_all_firing_requests()
    pro = await load_all_promotion_requests()
    wh = await load_all_warehouse_requests()
    dept = await load_all_department_transfer_requests()
    return req, fir, pro, wh, dept


async def log_db_state():
    try:
        req, fir, pro, wh, dept = await _load_all_tables_for_report()

        logger.info(
            "🗄️ БАЗА   | заявки=%s | увольнения=%s | повышения=%s | склад=%s | переводы=%s",
            len(req),
            len(fir),
            len(pro),
            len(wh),
            len(dept),
        )
    except Exception as e:
        logger.error("Отчёт состояния: ошибка чтения БД: %s", e, exc_info=True)


async def _validate_message_exists(channel: discord.TextChannel, message_id: int) -> bool:
    try:
        await channel.fetch_message(int(message_id))
        return True
    except discord.NotFound:
        return False
    except Exception:
        logger.debug("health_report _validate_message_exists: неожиданная ошибка при проверке сообщения", exc_info=True)
        return True  # не считаем это удалением, чтобы случайно не снести запись из БД


async def cleanup_orphan_records(bot: discord.Client, dry_run: bool = True):
    logger.info("🧹 Проверка осиротевших записей (только проверка=%s)...", dry_run)

    _fetch_semaphore = asyncio.Semaphore(5)

    async def validate_with_semaphore(channel: discord.TextChannel, message_id: int) -> bool:
        async with _fetch_semaphore:
            return await _validate_message_exists(channel, message_id)

    try:
        firing, promotion, warehouse = await asyncio.gather(
            load_all_firing_requests(),
            load_all_promotion_requests(),
            load_all_warehouse_requests(),
        )


        channel_cache = getattr(state, "channel_cache", None)
        if channel_cache is not None:
            firing_channel = await channel_cache.get_channel(Config.FIRING_CHANNEL_ID)
            warehouse_channel = await channel_cache.get_channel(Config.WAREHOUSE_REQUEST_CHANNEL_ID)
        else:
            firing_channel = bot.get_channel(Config.FIRING_CHANNEL_ID)
            warehouse_channel = bot.get_channel(Config.WAREHOUSE_REQUEST_CHANNEL_ID)

        promo_channels = []
        for cid in (getattr(Config, "PROMOTION_CHANNELS", {}) or {}).keys():
            if channel_cache is not None:
                ch = await channel_cache.get_channel(int(cid))
            else:
                ch = bot.get_channel(int(cid))
            if ch:
                promo_channels.append(ch)


        if firing_channel:
            for msg_id in list(firing.keys()):
                exists = await validate_with_semaphore(firing_channel, int(msg_id))
                if not exists:
                    logger.warning("🧹 ЛИШНЯЯ ЗАПИСЬ (увольнение): message_id=%s (сообщение удалено)", msg_id)
                    if not dry_run:
                        await delete_request("firing_requests", int(msg_id))


        if warehouse_channel:
            for msg_id in list(warehouse.keys()):
                exists = await validate_with_semaphore(warehouse_channel, int(msg_id))
                if not exists:
                    logger.warning("🧹 ЛИШНЯЯ ЗАПИСЬ (склад): message_id=%s (сообщение удалено)", msg_id)
                    if not dry_run:
                        await delete_request("warehouse_requests", int(msg_id))


        for msg_id in list(promotion.keys()):
            found = False
            for ch in promo_channels:
                try:
                    ok = await validate_with_semaphore(ch, int(msg_id))
                    if ok:
                        found = True
                        break
                except Exception:
                    logger.debug("cleanup_orphan_records: ошибка проверки сообщения повышения msg_id=%s", msg_id, exc_info=True)
                    continue

            if not found:
                logger.warning("🧹 ЛИШНЯЯ ЗАПИСЬ (повышение): message_id=%s (сообщение удалено)", msg_id)
                if not dry_run:
                    await delete_request("promotion_requests", int(msg_id))


        apply_channel_ids = [
            getattr(Config, "CHANNEL_APPLY_GROM", 0),
            getattr(Config, "CHANNEL_APPLY_PPS", 0),
            getattr(Config, "CHANNEL_APPLY_OSB", 0),
            getattr(Config, "CHANNEL_APPLY_ORLS", 0),
        ]
        apply_channel_ids = [c for c in apply_channel_ids if c]
        dept_transfers = await load_all_department_transfer_requests()
        for msg_id in list(dept_transfers.keys()):
            found = False
            for ch_id in apply_channel_ids:
                if channel_cache is not None:
                    ch = await channel_cache.get_channel(ch_id)
                else:
                    ch = bot.get_channel(ch_id)
                if ch and await validate_with_semaphore(ch, int(msg_id)):
                    found = True
                    break
            if not found:
                logger.warning("🧹 ЛИШНЯЯ ЗАПИСЬ (заявка перевод): message_id=%s (сообщение удалено)", msg_id)
                if not dry_run:
                    await delete_department_transfer_request(int(msg_id))
                    state.active_department_transfers.pop(int(msg_id), None)

        logger.info("🧹 Проверка лишних записей завершена")

    except Exception as e:
        logger.error("Отчёт состояния: ошибка проверки лишних записей: %s", e, exc_info=True)


async def run_health_report(bot: discord.Client):
    logger.info("========== ОТЧЁТ О СОСТОЯНИИ ==========")
    log_memory_state()
    await log_db_state()
    await cleanup_orphan_records(bot, dry_run=True)
    logger.info("======== ОТЧЁТ О СОСТОЯНИИ ГОТОВ ========")