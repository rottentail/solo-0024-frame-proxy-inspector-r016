from __future__ import annotations

import fcntl
import threading
from pathlib import Path
from types import TracebackType


_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[key] = lock
        return lock


class FileKeyLock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._thread_lock = _thread_lock(path)
        self._handle = None

    def __enter__(self) -> "FileKeyLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock.acquire()
        self._handle = self._path.open("a+b")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
        self._thread_lock.release()

