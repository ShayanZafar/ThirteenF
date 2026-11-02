"""One update at a time: a lock on data/update.lock held for the whole run.

The scheduled refresh and an update started by hand would otherwise write the same
files and wait on each other's database lock until one of them failed part way. The
lock is the operating system's (fcntl on macOS and Linux, msvcrt on Windows), so it
goes away with the process that held it: a crash or a closed window never leaves a
stale lock behind.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from thirteenf import config


class UpdateRunning(RuntimeError):
    """Another update holds the lock."""


def lock_path() -> Path:
    return config.DATA_DIR / "update.lock"


def _try_lock(fd: int) -> bool:
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


@contextmanager
def held(what: str) -> Iterator[None]:
    """Hold the update lock while the block runs; raise UpdateRunning at once if another
    process holds it. `what` is written into the file, so a person can see who has it."""
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if not _try_lock(fd):
            try:  # Windows refuses to read the locked byte; the note after it can still be read
                with open(path, "rb") as f:
                    f.seek(1)
                    holder = f.read().decode("utf-8", "replace").strip()
            except OSError:
                holder = ""
            raise UpdateRunning(f"Another update is running ({holder or 'started earlier'}); try again when it ends.")
        os.ftruncate(fd, 0)
        os.lseek(fd, 1, os.SEEK_SET)  # msvcrt locks the first byte; the note goes after it
        os.write(fd, f"{what}, process {os.getpid()}, since {datetime.now(UTC).isoformat(timespec='seconds')}".encode())
        yield
    finally:
        os.close(fd)
