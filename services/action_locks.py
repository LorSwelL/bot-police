import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


_locks: dict[int, asyncio.Lock] = {}
_dict_lock = asyncio.Lock()

_MAX_LOCKS_BEFORE_CLEANUP = 500


async def _get_lock(message_id: int) -> asyncio.Lock:
    msg_id = int(message_id)
    async with _dict_lock:
        if len(_locks) >= _MAX_LOCKS_BEFORE_CLEANUP:
            to_remove = [mid for mid, lk in list(_locks.items()) if not lk.locked()]
            for mid in to_remove:
                _locks.pop(mid, None)
            if to_remove:
                logger.debug("🧹 Очистка action_locks: удалено %s незаблокированных", len(to_remove))
        lock = _locks.get(msg_id)
        if lock is None:
            lock = asyncio.Lock()
            _locks[msg_id] = lock
        return lock


async def _cleanup_lock(message_id: int, lock: asyncio.Lock) -> None:
    msg_id = int(message_id)
    async with _dict_lock:
        current = _locks.get(msg_id)
        if current is lock and not lock.locked():
            _locks.pop(msg_id, None)
            logger.debug("🧹 Лок удалён из кеша: message_id=%s", msg_id)


def is_locked(message_id: int) -> bool:
    lock = _locks.get(int(message_id))
    return lock.locked() if lock else False


def locks_count() -> int:
    return len(_locks)


@asynccontextmanager
async def action_lock(message_id: int, action_name: str = "action"):
    msg_id = int(message_id)
    lock = await _get_lock(msg_id)

    if lock.locked():
        logger.warning(
            "🔒 Повторное действие заблокировано: %s | message_id=%s",
            action_name,
            msg_id
        )
        raise RuntimeError("ACTION_ALREADY_IN_PROGRESS")

    await lock.acquire()
    logger.info("🔒 Лок установлен: %s | message_id=%s", action_name, msg_id)

    try:
        yield
    finally:
        try:
            if lock.locked():
                lock.release()
                logger.info("🔓 Лок снят: %s | message_id=%s", action_name, msg_id)
        except Exception:
            logger.exception("❌ Ошибка при снятии лока: %s | message_id=%s", action_name, msg_id)
        finally:
            await _cleanup_lock(msg_id, lock)