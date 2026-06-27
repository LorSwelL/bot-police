import logging
import asyncio
from datetime import datetime, timedelta

import state
from config import Config
from database import cleanup_old_requests_db, cleanup_old_orls_drafts, cleanup_old_osb_drafts, cleanup_old_grom_drafts, cleanup_old_pps_drafts, cleanup_old_academy_drafts, optimize_db

logger = logging.getLogger(__name__)


class CleanupManager:

    def __init__(self, bot):
        self.bot = bot
        self.check_interval = 3600  # раз в час
        self._last_db_optimize_at: datetime | None = None
        self._last_db_vacuum_at: datetime | None = None

    def _cleanup_store_by_date(self, store: dict, name: str, cutoff: datetime) -> int:
        if not store:
            return 0

        to_delete = []
        for mid, data in list(store.items()):
            created = (data or {}).get("created_at")
            if not created:
                to_delete.append(mid)
                continue

            try:
                if datetime.fromisoformat(created) < cutoff:
                    to_delete.append(mid)
            except (ValueError, TypeError):
                to_delete.append(mid)

        for mid in to_delete:
            store.pop(mid, None)

        if to_delete:
            logger.info("🧹 Очищено %s старых записей: %s", len(to_delete), name)

        return len(to_delete)

    async def cleanup(self):
        try:
            cutoff = datetime.now() - timedelta(days=Config.REQUEST_EXPIRY_DAYS)


            self._cleanup_store_by_date(getattr(state, "active_requests", {}), "заявки", cutoff)
            self._cleanup_store_by_date(getattr(state, "active_firing_requests", {}), "увольнения", cutoff)
            self._cleanup_store_by_date(getattr(state, "active_promotion_requests", {}), "повышения", cutoff)
            self._cleanup_store_by_date(getattr(state, "warehouse_requests", {}), "склад", cutoff)
            self._cleanup_store_by_date(getattr(state, "active_department_transfers", {}), "переводы отделов", cutoff)


            await cleanup_old_requests_db(Config.REQUEST_EXPIRY_DAYS)

            # Опциональная оптимизация SQLite (не трогает данные)
            try:
                now = datetime.now()
                optimize_hours = int(getattr(Config, "DB_OPTIMIZE_INTERVAL_HOURS", 24) or 0)
                vacuum_days = int(getattr(Config, "DB_VACUUM_INTERVAL_DAYS", 0) or 0)

                if optimize_hours > 0:
                    due_opt = (
                        self._last_db_optimize_at is None
                        or (now - self._last_db_optimize_at).total_seconds() >= optimize_hours * 3600
                    )
                    if due_opt:
                        await optimize_db(vacuum=False)
                        self._last_db_optimize_at = now
                        logger.info("🧠 SQLite optimize выполнен")

                if vacuum_days > 0:
                    due_vac = (
                        self._last_db_vacuum_at is None
                        or (now - self._last_db_vacuum_at).total_seconds() >= vacuum_days * 86400
                    )
                    if due_vac:
                        await optimize_db(vacuum=True)
                        self._last_db_vacuum_at = now
                        logger.info("🧠 SQLite VACUUM выполнен")
            except Exception as e:
                logger.warning("SQLite optimize/vacuum пропущен из-за ошибки: %s", e, exc_info=True)


            orls_days = getattr(Config, "ORLS_DRAFT_EXPIRY_DAYS", 14)
            orls_deleted = await cleanup_old_orls_drafts(orls_days)
            if orls_deleted:
                logger.info("🧹 Удалено черновиков ОРЛС (старше %s дней): %s", orls_days, orls_deleted)


            osb_days = getattr(Config, "OSB_DRAFT_EXPIRY_DAYS", 14)
            osb_deleted = await cleanup_old_osb_drafts(osb_days)
            if osb_deleted:
                logger.info("🧹 Удалено черновиков ОСБ (старше %s дней): %s", osb_days, osb_deleted)


            grom_days = getattr(Config, "GROM_DRAFT_EXPIRY_DAYS", 14)
            grom_deleted = await cleanup_old_grom_drafts(grom_days)
            if grom_deleted:
                logger.info("🧹 Удалено черновиков ГРОМ (старше %s дней): %s", grom_days, grom_deleted)


            pps_days = getattr(Config, "PPS_DRAFT_EXPIRY_DAYS", 14)
            pps_deleted = await cleanup_old_pps_drafts(pps_days)
            if pps_deleted:
                logger.info("🧹 Удалено черновиков ППС (старше %s дней): %s", pps_days, pps_deleted)

            academy_days = getattr(Config, "ACADEMY_DRAFT_EXPIRY_DAYS", 14)
            academy_deleted = await cleanup_old_academy_drafts(academy_days)
            if academy_deleted:
                logger.info("🧹 Удалено черновиков Академии (старше %s дней): %s", academy_days, academy_deleted)

            try:
                from services.warehouse_session import WarehouseSession
                purged = await WarehouseSession.purge_expired(max_age_hours=24)
                if purged:
                    logger.info("🧹 Очищено просроченных сессий склада: %s", purged)
            except Exception as e:
                logger.warning("Очистка сессий склада: %s", e)

            logger.info("🧹 Периодическая очистка завершена")

        except asyncio.CancelledError:
            # Позволяем корректно остановить фоновую задачу очистки при shutdown.
            raise
        except Exception as e:
            logger.error("Ошибка при очистке: %s", e, exc_info=True)

    async def start_cleanup(self):
        await self.bot.wait_until_ready()
        # Первый запуск очистки откладываем на интервал, чтобы стартовые логи
        # завершались строкой startup_log.done().
        try:
            await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            logger.info("Фоновая задача очистки остановлена по CancelledError")
            raise

        while not self.bot.is_closed():
            try:
                await self.cleanup()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("Фоновая задача очистки остановлена по CancelledError")
                raise