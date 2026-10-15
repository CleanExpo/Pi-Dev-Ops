"""Owner-only, create-new log files for mesh runs, split out of run_record.py at the 300-line
convention (UNI-2963 review r8). run_record imports it as `_open_private`, where tests patch it."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def open_private(path: Path) -> Any:
    """Create `path` new, owner-only from the first byte, or return DEVNULL.

    O_EXCL: an existing file at this path — an earlier run's transcript under a
    repeated id, or a hard link planted there — is never opened, let alone
    truncated. The run then goes ahead without a log. The mode is set at
    creation, so there is no window with the umask's wider mode. Any failure
    after creating the file removes it.

    O_NOFOLLOW and fchmod do not exist on Windows (RA-7801): there the flag is
    left out and the mode given to os.open is the only one applied. O_EXCL still
    refuses anything already at the path, symlink included.
    """
    fd = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        return os.fdopen(fd, "wb")
    except OSError:
        if fd >= 0:
            os.close(fd)
            try:
                path.unlink()
            except OSError:
                pass
        return subprocess.DEVNULL
