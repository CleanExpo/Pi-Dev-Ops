"""Board and state file access for the red-main watcher (RA-8174).

update_jobs() follows the Guardian writer protocol (~/.local/bin/jobs_lock.py):
fcntl LOCK_EX on <jobs.json>.lock across the whole read-modify-write, then an atomic
replace that keeps the file's mode. Every jobs.json writer takes the same lock, so
no row is lost. single_run() keeps two watcher cycles from overlapping, which is
what makes "one lane per red episode" hold.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import stat
import tempfile
import time

from red_main.common import ops_dir, state_dir


def jobs_path() -> str:
    return os.path.join(ops_dir(), "jobs.json")


@contextlib.contextmanager
def _flock(path: str, timeout: float):
    deadline = time.time() + timeout
    with open(path, "a") as lk:
        while True:
            try:
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    raise TimeoutError(f"could not lock {path} within {timeout}s") from None
                time.sleep(0.02)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def _atomic_write(path: str, data, mode: int | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".red-main-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def update_jobs(mutate, timeout: float = 60.0) -> bool:
    """mutate(d) -> truthy when changed. A raising mutate leaves the file untouched."""
    path = jobs_path()
    with _flock(path + ".lock", timeout):
        with open(path) as f:
            d = json.load(f)
        if not mutate(d):
            return False
        _atomic_write(path, d, stat.S_IMODE(os.stat(path).st_mode))
        return True


def read_jobs() -> dict:
    with open(jobs_path()) as f:
        return json.load(f)


def state_file(name: str) -> str:
    return os.path.join(state_dir(), name)


def load_state(name: str) -> dict:
    try:
        with open(state_file(name)) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(name: str, data: dict) -> None:
    _atomic_write(state_file(name), data)


@contextlib.contextmanager
def single_run():
    """Yields True when this process holds the watcher lock, False when another cycle does."""
    os.makedirs(state_dir(), exist_ok=True)
    with open(state_file("red-main-watch.lock"), "a") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
