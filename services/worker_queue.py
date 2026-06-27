import asyncio
import inspect
import logging
from typing import Any, Callable, Coroutine, TypeVar, Union

logger = logging.getLogger(__name__)

T = TypeVar("T")

MAX_QUEUE_SIZE = 2000


class WorkerQueue:
    def __init__(self, max_size: int = MAX_QUEUE_SIZE):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._worker_task: asyncio.Task | None = None
        self._running = False
    
    def _ensure_started(self) -> None:
        """
        Гарантировать, что воркер запущен.
        Важно: submit()/submit_fire() часто вызываются из обработчиков интеракций,
        где ожидание Future критично — если воркер не запущен, Future никогда не завершится.
        """
        if self._running and self._worker_task is not None:
            return
        try:
            self.start()
        except RuntimeError as e:
            # create_task требует запущенного event loop; если submit вызван вне loop,
            # пусть вызывающий код увидит исходную проблему.
            logger.error("Не удалось автозапустить воркер очереди задач: %s", e, exc_info=True)
            raise

    def submit(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> asyncio.Future[T]:
        self._ensure_started()
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        try:
            self._queue.put_nowait((fn, args, kwargs, future))
        except asyncio.QueueFull:
            future.set_exception(RuntimeError("Очередь задач переполнена"))
        return future

    def submit_fire(
        self,
        fn: Union[Callable[..., Any], Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        # fire-and-forget тоже должен выполняться; иначе важные операции (например, чистка черновиков)
        # будут бесследно копиться в памяти, если воркер не запущен.
        self._ensure_started()
        try:
            self._queue.put_nowait((fn, args, kwargs, None))
        except asyncio.QueueFull:
            logger.warning("Очередь воркера переполнена, задача %s пропущена", getattr(fn, "__name__", fn))

    async def _run_worker(self) -> None:
        try:
            while self._running:
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                fn, args, kwargs, future = item
                try:
                    if asyncio.iscoroutine(fn):
                        result = await fn
                    elif inspect.iscoroutinefunction(fn):
                        result = await fn(*args, **kwargs)
                    else:
                        result = await asyncio.to_thread(fn, *args, **kwargs)
                    if future is not None and not future.done():
                        future.set_result(result)
                except Exception as e:
                    if future is not None and not future.done():
                        future.set_exception(e)
                    else:
                        logger.error(
                            "Воркер: ошибка в задаче (fire-and-forget) %s: %s",
                            getattr(fn, "__name__", fn),
                            e,
                            exc_info=True,
                        )
        except asyncio.CancelledError:
            logger.info("Воркер очереди задач остановлен по CancelledError")
            raise
        except Exception as e:
            # Неожиданное падение самого воркера — критично для фоновых операций.
            logger.critical("Фоновый воркер очереди задач упал: %s", e, exc_info=True)
            self._running = False

    def start(self) -> None:
        if self._worker_task is not None:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._run_worker())
        logger.info("Воркер очереди задач запущен")

    def stop(self) -> None:
        if not self._running and self._worker_task is None:
            return
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            self._worker_task = None
        logger.info("Воркер очереди задач остановлен")


worker: WorkerQueue | None = None


def get_worker() -> WorkerQueue:
    global worker
    if worker is None:
        worker = WorkerQueue(max_size=MAX_QUEUE_SIZE)
        logger.debug("Воркер очереди задач создан (ленивая инициализация)")
    return worker


def init_worker(max_size: int = MAX_QUEUE_SIZE) -> WorkerQueue:
    global worker
    if worker is not None:
        return worker
    worker = WorkerQueue(max_size=max_size)
    return worker
