from __future__ import annotations

import atexit
import os
from pathlib import Path

from app.paths import RUNTIME_DIR

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class SingleInstanceLock:
    """Best-effort process lock stored in the runtime directory."""

    def __init__(self, name: str) -> None:
        self.path = RUNTIME_DIR / name
        self._handle = None
        self._registered = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+", encoding="utf-8")
        try:
            handle.seek(0)
            if not handle.read(1):
                handle.seek(0)
                handle.write("0")
                handle.flush()
            handle.seek(0)

            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()

        self._handle = handle
        if not self._registered:
            atexit.register(self.release)
            self._registered = True
        return True

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return

        try:
            handle.seek(0)
            handle.truncate()
            handle.write("0")
            handle.flush()

            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            handle.close()
            self._handle = None
