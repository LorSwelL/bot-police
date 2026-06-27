import logging
import asyncio
import discord

from views.firing_view import FiringView
from views.promotion_view import PromotionView
from views.start_view import StartView
from views.warehouse_start import WarehouseStartView
from views.request_view import RequestView
from views.warehouse_request_buttons import WarehouseRequestView
from views.department_approval_view import DepartmentApprovalView
from views.apply_channel_view import ApplyChannelView
from views.academy_apply_view import AcademyApplyView
from views.academy_promotion_apply_view import AcademyPromotionApplyView
from views.orls_promotion_apply_view import OrlsPromotionApplyView
from services.position_admin_transfer import AdminTransferView
from services.firing_position_manager import FiringStartView

import state
from config import Config
from enums import RequestType
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


class ViewRestorer:
    def __init__(self, bot):
        self.bot = bot
        self._fetch_semaphore = asyncio.Semaphore(5)

    async def _bounded_fetch_message(self, channel: discord.abc.Messageable, message_id: int):
        """
        Ограниченный по параллелизму fetch_message, чтобы не забивать Discord API.
        """
        async with self._fetch_semaphore:
            return await channel.fetch_message(message_id)

    async def restore_all(self):
        logger.info("Восстановление View...")

        self._restore_start_views()
        await self._load_requests_from_db()


        await asyncio.gather(
            self._restore_request_views(),
            self._restore_firing_views(),
            self._restore_promotion_views(),
            self._restore_warehouse_views(),
            self._restore_department_transfer_views(),
        )

        logger.info("Восстановление View завершено")

    def _restore_start_views(self):



        self.bot.add_view(StartView())
        self.bot.add_view(WarehouseStartView())

        self.bot.add_view(ApplyChannelView("grom", [("pps", "「ППС」"), ("orls", "「ОРЛС」"), ("osb", "「ОСБ」")]))
        self.bot.add_view(ApplyChannelView("pps", [("grom", "「ГРОМ」"), ("orls", "「ОРЛС」"), ("osb", "「ОСБ」")]))
        self.bot.add_view(ApplyChannelView("osb", [("pps", "「ППС」"), ("orls", "「ОРЛС」"), ("grom", "「ГРОМ」")]))
        self.bot.add_view(ApplyChannelView("orls", [("pps", "「ППС」"), ("grom", "「ГРОМ」"), ("osb", "「ОСБ」")]))
        self.bot.add_view(AcademyApplyView())
        self.bot.add_view(AcademyPromotionApplyView())
        self.bot.add_view(AdminTransferView())

        self.bot.add_view(FiringStartView())

        self.bot.add_view(OrlsPromotionApplyView())

        from views.osb_promotion_apply_view import OsbPromotionApplyView
        self.bot.add_view(OsbPromotionApplyView())

        from views.grom_promotion_apply_view import GromPromotionApplyView
        self.bot.add_view(GromPromotionApplyView())

        from views.pps_promotion_apply_view import PpsPromotionApplyView
        self.bot.add_view(PpsPromotionApplyView())
        logger.info("Стартовые View восстановлены")

    async def _load_requests_from_db(self):
        raw_max = getattr(Config, "RESTORE_MAX_ITEMS", 1000)
        max_items = raw_max if (raw_max is not None and raw_max > 0) else 1000
        max_days = getattr(Config, "RESTORE_MAX_DAYS", 0) or None

        # Заявки пользователей
        try:
            store = getattr(state, "request_store", None)
        except Exception:
            logger.debug("restore_views _load_requests_from_db: не удалось получить request_store", exc_info=True)
            store = None
        if store is not None:
            try:
                data = await store.list_for_restore(max_days=max_days, limit=max_items)
            except Exception as e:
                logger.error("Ошибка list_for_restore для заявок: %s", e, exc_info=True)
                data = await load_all_requests()
        else:
            try:
                data = await load_all_requests()
            except Exception as e:
                logger.error("Ошибка загрузки active_requests из БД: %s", e, exc_info=True)
                data = getattr(state, "active_requests", None) or {}
        target = getattr(state, "active_requests", None) or {}
        target.clear()
        target.update(data or {})

        # Увольнения
        try:
            firing_store = getattr(state, "firing_store", None)
        except Exception:
            logger.debug("restore_views _load_requests_from_db: не удалось получить firing_store", exc_info=True)
            firing_store = None
        if firing_store is not None:
            try:
                data = await firing_store.list_for_restore(max_days=max_days, limit=max_items)
            except Exception as e:
                logger.error("Ошибка list_for_restore для увольнений: %s", e, exc_info=True)
                data = await load_all_firing_requests()
        else:
            try:
                data = await load_all_firing_requests()
            except Exception as e:
                logger.error("Ошибка загрузки active_firing_requests из БД: %s", e, exc_info=True)
                data = getattr(state, "active_firing_requests", None) or {}
        target = getattr(state, "active_firing_requests", None) or {}
        target.clear()
        target.update(data or {})

        # Повышения
        try:
            promo_store = getattr(state, "promotion_store", None)
        except Exception:
            logger.debug("restore_views _load_requests_from_db: не удалось получить promotion_store", exc_info=True)
            promo_store = None
        if promo_store is not None:
            try:
                data = await promo_store.list_for_restore(max_days=max_days, limit=max_items)
            except Exception as e:
                logger.error("Ошибка list_for_restore для повышений: %s", e, exc_info=True)
                data = await load_all_promotion_requests()
        else:
            try:
                data = await load_all_promotion_requests()
            except Exception as e:
                logger.error("Ошибка загрузки active_promotion_requests из БД: %s", e, exc_info=True)
                data = getattr(state, "active_promotion_requests", None) or {}
        target = getattr(state, "active_promotion_requests", None) or {}
        target.clear()
        target.update(data or {})

        # Склад
        try:
            wh_store = getattr(state, "warehouse_store", None)
        except Exception:
            logger.debug("restore_views _load_requests_from_db: не удалось получить warehouse_store", exc_info=True)
            wh_store = None
        if wh_store is not None:
            try:
                data = await wh_store.list_for_restore(max_days=max_days, limit=max_items)
            except Exception as e:
                logger.error("Ошибка list_for_restore для склада: %s", e, exc_info=True)
                data = await load_all_warehouse_requests()
        else:
            try:
                data = await load_all_warehouse_requests()
            except Exception as e:
                logger.error("Ошибка загрузки warehouse_requests из БД: %s", e, exc_info=True)
                data = getattr(state, "warehouse_requests", None) or {}
        target = getattr(state, "warehouse_requests", None) or {}
        target.clear()
        target.update(data or {})

        # Переводы между отделами — применяем те же лимиты RESTORE_MAX_ITEMS / RESTORE_MAX_DAYS
        try:
            transfers = await load_all_department_transfer_requests()
        except Exception as e:
            logger.error("Ошибка загрузки active_department_transfers из БД: %s", e, exc_info=True)
            transfers = getattr(state, "active_department_transfers", None) or {}
        if max_days or (max_items is not None and max_items > 0):
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(days=max_days)) if max_days else None
            prepared = []
            for mid, raw in (transfers or {}).items():
                data = dict(raw or {})
                created_raw = data.get("created_at")
                if isinstance(created_raw, str):
                    try:
                        created_dt = datetime.fromisoformat(created_raw)
                    except (ValueError, TypeError):
                        created_dt = datetime.min
                elif isinstance(created_raw, datetime):
                    created_dt = created_raw
                else:
                    created_dt = datetime.min
                if cutoff is not None and created_dt != datetime.min and created_dt < cutoff:
                    continue
                try:
                    mid_int = int(mid)
                except (TypeError, ValueError):
                    continue
                prepared.append((mid_int, data, created_dt))
            prepared.sort(key=lambda t: t[2], reverse=True)
            if max_items and len(prepared) > max_items:
                prepared = prepared[:max_items]
            transfers = {mid: data for mid, data, _ in prepared}
        target = getattr(state, "active_department_transfers", None) or {}
        target.clear()
        target.update(transfers or {})

        logger.info(
            "📦 Загружено из БД: заявок=%s, увольнений=%s, повышений=%s, склад=%s, переводы=%s",
            len(getattr(state, "active_requests", {}) or {}),
            len(getattr(state, "active_firing_requests", {}) or {}),
            len(getattr(state, "active_promotion_requests", {}) or {}),
            len(getattr(state, "warehouse_requests", {}) or {}),
            len(getattr(state, "active_department_transfers", {}) or {}),
        )

    async def _delete_orphan(self, storage: dict, table_name: str, msg_id, reason: str = ""):
        try:
            msg_id_int = int(msg_id)
        except (TypeError, ValueError):
            logger.warning("⚠️ Некорректный message_id для удаления (%s): %r", table_name, msg_id)
            return False

        try:
            await delete_request(table_name, msg_id_int)
            storage.pop(msg_id_int, None)
            logger.info("🧹 Удалена осиротевшая запись %s msg_id=%s %s", table_name, msg_id_int, f"({reason})" if reason else "")
            return True
        except Exception as e:
            logger.error("❌ Не удалось удалить запись %s msg_id=%s: %s", table_name, msg_id_int, e, exc_info=True)
            return False

    async def _restore_request_views(self):
        channel = self.bot.get_channel(Config.REQUEST_CHANNEL_ID)
        if not channel:
            logger.warning("⚠️ Канал заявок не найден: %s", Config.REQUEST_CHANNEL_ID)
            return

        restored = 0
        deleted = 0
        skipped = 0
        storage = (getattr(state, "active_requests", {}) or {})
        total = len(storage)

        batch_size = getattr(Config, "RESTORE_BATCH_SIZE", 0) or 0
        batch_delay = getattr(Config, "RESTORE_BATCH_DELAY_SEC", 0) or 0
        processed = 0

        for msg_id, data in list(storage.items()):
            try:
                msg_id_int = int(msg_id)
            except (TypeError, ValueError):
                logger.warning("⚠️ Битый message_id в active_requests: %r", msg_id)
                skipped += 1
                continue

            rt_raw = str((data or {}).get("request_type") or "").strip().lower()
            if not rt_raw:
                logger.warning("⚠️ Пустой request_type для msg_id=%s", msg_id_int)
                skipped += 1
                continue

            try:
                request_type = RequestType(rt_raw)
            except ValueError:
                logger.warning("⚠️ Неизвестный request_type='%s' для message_id=%s", rt_raw, msg_id_int)
                skipped += 1
                continue

            try:
                user_id = int((data or {}).get("user_id", 0))
                if not user_id:
                    logger.warning("⚠️ Некорректный user_id для msg_id=%s", msg_id_int)
                    skipped += 1
                    continue

                try:
                    await self._bounded_fetch_message(channel, msg_id_int)
                except discord.NotFound:
                    if await self._delete_orphan(state.active_requests, "requests", msg_id_int, "сообщение удалено"):
                        deleted += 1
                    else:
                        skipped += 1
                    continue
                except discord.Forbidden:
                    logger.warning("⚠️ Нет доступа к сообщению заявки msg_id=%s", msg_id_int)
                    skipped += 1
                    continue
                except discord.HTTPException as e:
                    logger.warning("⚠️ HTTP ошибка при fetch заявки msg_id=%s: %s", msg_id_int, e)
                    skipped += 1
                    continue

                view = RequestView(
                    user_id=user_id,
                    validated_data=data,
                    request_type=request_type,
                )
                self.bot.add_view(view, message_id=msg_id_int)
                restored += 1

            except (TypeError, ValueError) as e:
                logger.warning("⚠️ Некорректные данные заявки msg_id=%s: %s", msg_id_int, e)
                skipped += 1
            except Exception as e:
                logger.warning("⚠️ Не удалось восстановить заявку msg_id=%s: %s", msg_id_int, e, exc_info=True)
                skipped += 1

            processed += 1
            if batch_size > 0 and batch_delay > 0 and processed % batch_size == 0:
                logger.info(
                    "Восстановление заявок: обработано %s/%s (restored=%s, deleted=%s, skipped=%s)",
                    processed,
                    total,
                    restored,
                    deleted,
                    skipped,
                )
                await asyncio.sleep(batch_delay)

        logger.info(
            "🔨 Восстановлено кнопок заявок: %s | удалено из БД: %s | пропущено: %s",
            restored, deleted, skipped
        )

    async def _restore_firing_views(self):
        channel = self.bot.get_channel(Config.FIRING_CHANNEL_ID)
        if not channel:
            logger.warning("⚠️ Канал увольнений не найден: %s", Config.FIRING_CHANNEL_ID)
            return

        restored = 0
        deleted = 0
        skipped = 0
        storage = (getattr(state, "active_firing_requests", {}) or {})
        total = len(storage)

        batch_size = getattr(Config, "RESTORE_BATCH_SIZE", 0) or 0
        batch_delay = getattr(Config, "RESTORE_BATCH_DELAY_SEC", 0) or 0
        processed = 0

        for msg_id, data in list(storage.items()):
            try:
                msg_id_int = int(msg_id)
                user_id = int((data or {}).get("discord_id", 0))
            except (TypeError, ValueError):
                logger.warning("⚠️ Битые данные увольнения msg_id=%r", msg_id)
                if await self._delete_orphan(state.active_firing_requests, "firing_requests", msg_id, "битый ID/данные"):
                    deleted += 1
                else:
                    skipped += 1
                continue

            if not user_id:
                logger.warning("⚠️ Пустой discord_id в увольнении msg_id=%s", msg_id_int)
                if await self._delete_orphan(state.active_firing_requests, "firing_requests", msg_id_int, "пустой discord_id"):
                    deleted += 1
                else:
                    skipped += 1
                continue

            try:
                await self._bounded_fetch_message(channel, msg_id_int)
            except discord.NotFound:
                if await self._delete_orphan(state.active_firing_requests, "firing_requests", msg_id_int, "сообщение удалено"):
                    deleted += 1
                else:
                    skipped += 1
                continue
            except discord.Forbidden:
                logger.warning("⚠️ Нет доступа к сообщению увольнения msg_id=%s", msg_id_int)
                skipped += 1
                continue
            except discord.HTTPException as e:
                logger.warning("⚠️ HTTP ошибка при fetch увольнения msg_id=%s: %s", msg_id_int, e)
                skipped += 1
                continue

            try:
                view = FiringView(user_id=user_id)
                self.bot.add_view(view, message_id=msg_id_int)
                restored += 1
            except Exception as e:
                logger.warning("⚠️ Ошибка восстановления увольнения msg_id=%s: %s", msg_id_int, e, exc_info=True)
                skipped += 1

            processed += 1
            if batch_size > 0 and batch_delay > 0 and processed % batch_size == 0:
                logger.info(
                    "Восстановление увольнений: обработано %s/%s (restored=%s, deleted=%s, skipped=%s)",
                    processed,
                    total,
                    restored,
                    deleted,
                    skipped,
                )
                await asyncio.sleep(batch_delay)

        logger.info(
            "🔨 Восстановлено кнопок увольнений: %s | удалено из БД: %s | пропущено: %s",
            restored, deleted, skipped
        )

    async def _restore_promotion_views(self):
        restored = 0
        deleted = 0
        skipped = 0

        channel_ids = list(Config.PROMOTION_CHANNELS.keys()) if isinstance(Config.PROMOTION_CHANNELS, dict) else []
        channels = {cid: self.bot.get_channel(cid) for cid in channel_ids}

        storage = (getattr(state, "active_promotion_requests", {}) or {})
        total = len(storage)

        batch_size = getattr(Config, "RESTORE_BATCH_SIZE", 0) or 0
        batch_delay = getattr(Config, "RESTORE_BATCH_DELAY_SEC", 0) or 0
        processed = 0

        for msg_id, data in list(storage.items()):
            try:
                msg_id_int = int(msg_id)
                discord_id = int((data or {}).get("discord_id", 0))
                new_rank = str((data or {}).get("new_rank") or "").strip()
                full_name = str((data or {}).get("full_name") or "сотрудник").strip() or "сотрудник"
            except (TypeError, ValueError):
                logger.warning("⚠️ Битые данные повышения msg_id=%r", msg_id)
                if await self._delete_orphan(state.active_promotion_requests, "promotion_requests", msg_id, "битый ID/данные"):
                    deleted += 1
                else:
                    skipped += 1
                continue

            if not discord_id or not new_rank:
                logger.warning("⚠️ Некорректные данные повышения msg_id=%s (discord_id/new_rank)", msg_id_int)
                if await self._delete_orphan(state.active_promotion_requests, "promotion_requests", msg_id_int, "нет discord_id/new_rank"):
                    deleted += 1
                else:
                    skipped += 1
                continue

            found = False
            for _, ch in channels.items():
                if not ch:
                    continue
                try:
                    await self._bounded_fetch_message(ch, msg_id_int)
                    found = True
                    break
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    logger.warning("⚠️ Нет доступа к каналу повышения при проверке msg_id=%s", msg_id_int)
                    continue
                except discord.HTTPException:
                    continue

            if not found:
                if await self._delete_orphan(state.active_promotion_requests, "promotion_requests", msg_id_int, "сообщение удалено"):
                    deleted += 1
                else:
                    skipped += 1
                continue

            try:
                view = PromotionView(
                    user_id=discord_id,
                    new_rank=new_rank,
                    full_name=full_name,
                    message_id=msg_id_int,
                )
                self.bot.add_view(view, message_id=msg_id_int)
                restored += 1
            except Exception as e:
                logger.warning("⚠️ Ошибка восстановления повышения msg_id=%s: %s", msg_id_int, e, exc_info=True)
                skipped += 1

            processed += 1
            if batch_size > 0 and batch_delay > 0 and processed % batch_size == 0:
                logger.info(
                    "Восстановление повышений: обработано %s/%s (restored=%s, deleted=%s, skipped=%s)",
                    processed,
                    total,
                    restored,
                    deleted,
                    skipped,
                )
                await asyncio.sleep(batch_delay)

        logger.info(
            "🔨 Восстановлено кнопок повышений: %s | удалено из БД: %s | пропущено: %s",
            restored, deleted, skipped
        )

    async def _restore_warehouse_views(self):
        channel = self.bot.get_channel(Config.WAREHOUSE_REQUEST_CHANNEL_ID)
        if not channel:
            logger.warning("⚠️ Канал склада не найден: %s", Config.WAREHOUSE_REQUEST_CHANNEL_ID)
            return

        restored = 0
        deleted = 0
        skipped = 0
        storage = (getattr(state, "warehouse_requests", {}) or {})
        total = len(storage)

        batch_size = getattr(Config, "RESTORE_BATCH_SIZE", 0) or 0
        batch_delay = getattr(Config, "RESTORE_BATCH_DELAY_SEC", 0) or 0
        processed = 0

        for msg_id, data in list(storage.items()):
            try:
                msg_id_int = int(msg_id)
                user_id = int((data or {}).get("user_id", 0))
            except (TypeError, ValueError):
                logger.warning("⚠️ Битые данные склада msg_id=%r", msg_id)
                if await self._delete_orphan(state.warehouse_requests, "warehouse_requests", msg_id, "битый ID/данные"):
                    deleted += 1
                else:
                    skipped += 1
                continue

            if not user_id:
                logger.warning("⚠️ Пустой user_id в заявке склада msg_id=%s", msg_id_int)
                if await self._delete_orphan(state.warehouse_requests, "warehouse_requests", msg_id_int, "пустой user_id"):
                    deleted += 1
                else:
                    skipped += 1
                continue

            try:
                await self._bounded_fetch_message(channel, msg_id_int)
            except discord.NotFound:
                if await self._delete_orphan(state.warehouse_requests, "warehouse_requests", msg_id_int, "сообщение удалено"):
                    deleted += 1
                else:
                    skipped += 1
                continue
            except discord.Forbidden:
                logger.warning("⚠️ Нет доступа к сообщению склада msg_id=%s", msg_id_int)
                skipped += 1
                continue
            except discord.HTTPException as e:
                logger.warning("⚠️ HTTP ошибка при fetch склада msg_id=%s: %s", msg_id_int, e)
                skipped += 1
                continue

            try:
                view = WarehouseRequestView(author_id=user_id, message_id=msg_id_int)
                self.bot.add_view(view, message_id=msg_id_int)
                restored += 1
            except Exception as e:
                logger.warning("⚠️ Ошибка восстановления склада msg_id=%s: %s", msg_id_int, e, exc_info=True)
                skipped += 1

            processed += 1
            if batch_size > 0 and batch_delay > 0 and processed % batch_size == 0:
                logger.info(
                    "Восстановление склада: обработано %s/%s (restored=%s, deleted=%s, skipped=%s)",
                    processed,
                    total,
                    restored,
                    deleted,
                    skipped,
                )
                await asyncio.sleep(batch_delay)

        logger.info(
            "🔨 Восстановлено кнопок склада: %s | удалено из БД: %s | пропущено: %s",
            restored, deleted, skipped
        )

    async def _restore_department_transfer_views(self):
        restored = 0
        deleted = 0
        skipped = 0

        apply_channel_ids = []
        for name in ("CHANNEL_APPLY_GROM", "CHANNEL_APPLY_PPS", "CHANNEL_APPLY_OSB", "CHANNEL_APPLY_ORLS"):
            ch_id = getattr(Config, name, 0)
            if ch_id:
                apply_channel_ids.append(ch_id)

        storage = list((getattr(state, "active_department_transfers", {}) or {}).items())
        total = len(storage)
        batch_size = getattr(Config, "RESTORE_BATCH_SIZE", 0) or 0
        batch_delay = getattr(Config, "RESTORE_BATCH_DELAY_SEC", 0) or 0
        processed = 0

        for msg_id, data in storage:
            try:
                msg_id_int = int(msg_id)
            except (TypeError, ValueError):
                logger.warning("⚠️ Битый message_id в active_department_transfers: %r", msg_id)
                skipped += 1
                continue

            approved_src = int(data.get("approved_source") or 0)
            approved_tgt = int(data.get("approved_target") or 0)
            if approved_src and approved_tgt:
                skipped += 1
                continue

            found = False
            found_channel_id = 0
            for ch_id in apply_channel_ids:
                ch = self.bot.get_channel(ch_id)
                if not ch:
                    continue
                try:
                    await self._bounded_fetch_message(ch, msg_id_int)
                    found = True
                    found_channel_id = ch_id
                    break
                except discord.NotFound:
                    continue
                except (discord.Forbidden, discord.HTTPException):
                    continue

            if not found:
                try:
                    await delete_department_transfer_request(msg_id_int)
                    deleted += 1
                    state.active_department_transfers.pop(msg_id_int, None)
                except Exception as e:
                    logger.warning("⚠️ Не удалось удалить осиротевшую заявку перевод msg_id=%s: %s", msg_id_int, e)
                    skipped += 1
                continue

            if not isinstance(data, dict):
                logger.warning("⚠️ Некорректные данные заявки перевод msg_id=%s: data не dict", msg_id_int)
                skipped += 1
                continue
            try:
                user_id_val = int(data.get("user_id", 0))
            except (TypeError, ValueError):
                logger.warning("⚠️ Некорректный user_id в заявке перевод msg_id=%s", msg_id_int)
                skipped += 1
                continue
            if not user_id_val:
                logger.warning("⚠️ Пустой user_id в заявке перевод msg_id=%s", msg_id_int)
                skipped += 1
                continue
            if not found_channel_id:
                logger.warning("⚠️ Не найден канал для заявки перевод msg_id=%s", msg_id_int)
                skipped += 1
                continue

            try:
                view = DepartmentApprovalView(
                    message_id=msg_id_int,
                    user_id=user_id_val,
                    target_dept=str(data.get("target_dept", "")),
                    source_dept=str(data.get("source_dept", "")),
                    from_academy=bool(data.get("from_academy")),
                    form_data=dict(data.get("data") or {}),
                    approved_source=approved_src,
                    approved_target=approved_tgt,
                    channel_id=found_channel_id,
                )
                self.bot.add_view(view, message_id=msg_id_int)
                restored += 1
            except Exception as e:
                logger.warning("⚠️ Ошибка восстановления заявки перевод msg_id=%s: %s", msg_id_int, e, exc_info=True)
                skipped += 1

            processed += 1
            if batch_size > 0 and batch_delay > 0 and processed % batch_size == 0:
                logger.info(
                    "Восстановление заявок на перевод: обработано %s/%s (restored=%s, deleted=%s, skipped=%s)",
                    processed,
                    total,
                    restored,
                    deleted,
                    skipped,
                )
                await asyncio.sleep(batch_delay)

        logger.info(
            "🔨 Восстановлено кнопок заявок на перевод: %s | удалено из БД: %s | пропущено: %s",
            restored, deleted, skipped
        )