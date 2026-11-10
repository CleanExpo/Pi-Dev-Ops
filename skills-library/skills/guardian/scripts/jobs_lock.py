"""Shared writer protocol for ops/jobs.json (Guardian, stdlib only, python 3.9 ok).
Same lock pc-board.py takes: fcntl.flock(LOCK_EX) on <jobs.json>.lock. Every writer of jobs.json
(watchers, pc-board) must hold it across the whole read-modify-write, or rows are silently lost.
update_jobs(path, mutate): lock, load, mutate(d) -> truthy if changed, atomic write (mkstemp + os.replace)."""
import fcntl, json, os, stat, tempfile, time
from contextlib import contextmanager


@contextmanager
def locked(jobs_path, timeout=60.0):
    deadline = time.time() + timeout
    with open(jobs_path + ".lock", "a") as lk:
        while True:
            try:
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() >= deadline:
                    raise TimeoutError(f"could not lock {jobs_path}.lock within {timeout}s")
                time.sleep(0.02)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def update_jobs(jobs_path, mutate, timeout=60.0):
    """Returns True if the file was rewritten. A raising mutate or unreadable jobs.json leaves the file as it was."""
    with locked(jobs_path, timeout):
        with open(jobs_path) as f:
            d = json.load(f)
        if not mutate(d):
            return False
        mode = stat.S_IMODE(os.stat(jobs_path).st_mode)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(jobs_path), prefix=".jobs-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(d, f, indent=1)
                f.flush(); os.fsync(f.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, jobs_path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return True
