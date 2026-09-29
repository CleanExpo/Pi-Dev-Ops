#!/usr/bin/env python3
"""Repair unguarded post-edit Prettier hooks in .codex/hooks.json.

THE DEFECT THIS FIXES. A PostToolUse Write|Edit hook of the form

    npx prettier --write "$CLAUDE_FILE_PATH" 2>/dev/null || true

does not format one file when CLAUDE_FILE_PATH is unset, empty, or names a
directory — prettier walks the tree instead. `2>/dev/null || true` swallows
every trace, so the only symptom is a working tree that has quietly grown
~1,345 modified tracked files. Reproduced 2026-07-29 against a scratch
directory: with the variable unset, both a top-level and a NESTED file were
reformatted.

Worse than the diff size: a `git add -A` commits all of it, and two independent
reviews of the RA-7090 branch ran against a tree that may have been reformatted
underneath them.

WHY IT LIVES HERE. `.codex/` is gitignored in every repo that has one, so the
fix cannot travel in a commit. This is the "wired is not synced" class from
AGENTS.md: the hook is machine-local, so the repair must be INSTALLED by
bootstrap, not assumed present.

Idempotent: a hooks file already carrying the guard is left untouched.
Exit 0 always — a repair failure must never fail bootstrap.
"""
import hashlib
import json
import os
import secrets
import stat
import sys
from pathlib import Path

# The guard: run only when the variable is non-empty AND names a regular file.
# -f closes the directory case as well as unset/empty. `|| true` stays INSIDE
# so a prettier failure still cannot fail the edit.
GUARDED = (
    'if [ -n "$CLAUDE_FILE_PATH" ] && [ -f "$CLAUDE_FILE_PATH" ]; then '
    'npx prettier --write "$CLAUDE_FILE_PATH" 2>/dev/null || true; fi'
)

# Search roots. Depth-limited so this stays fast on a large home directory.
ROOTS = [Path.home(), Path.home() / "Developer"]
MAX_DEPTH = 3


def _within_scan_roots(target: Path) -> bool:
    """True when `target` lies inside a declared scan root.

    Resolving a symlink is what makes the canonical file repairable, but a link can
    point anywhere — so the resolved path must be re-checked against the surface this
    script is allowed to touch. ROOTS are resolved too, so a symlinked $HOME does not
    produce a spurious mismatch.
    """
    try:
        target = target.resolve()
    except OSError:
        return False
    for root in ROOTS:
        try:
            target.relative_to(root.resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def _create_temp(dfd):
    """Create an unpredictably-named temp file inside the pinned directory.

    The temp name must be UNPREDICTABLE. A fixed `hooks.json.tmp` is a name an
    attacker (or a stale link) can pre-create as a symlink: writing then followed it
    and destroyed an unrelated file, leaving hooks.json pointing at the victim
    (review 2026-08-09: victim_overwritten=True, hooks_points_to_victim=True).
    O_CREAT|O_EXCL|O_NOFOLLOW at mode 0600, relative to the pinned dirfd, cannot
    follow a link and cannot land outside the confined directory.

    Returns the name (relative to `dfd`), or None if no name could be claimed.
    """
    for _ in range(10):
        candidate = f".hooks-repair-{secrets.token_hex(8)}.json.tmp"
        try:
            os.close(os.open(candidate,
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                             0o600, dir_fd=dfd))
            return candidate
        except FileExistsError:
            continue
        except OSError:
            return None
    return None


def _confined_parent_fd(target: Path):
    """Open `target`'s parent by descending from a scan root with no-follow opens.

    Checking confinement on a PATHNAME and then reopening that same pathname is a
    race: renaming an ancestor and dropping a symlink in its place redirected the
    whole repair outside ROOTS, and the window spanned the read, the parse, the temp
    write, the digest check, the chmod and the swap (review 2026-08-09, P1 —
    outside_repaired=True, inside_untouched=True). Descending component by component
    with O_NOFOLLOW and keeping the resulting descriptor pins the real directory
    INODE, so a later swap of any ancestor cannot redirect the operations that follow:
    every one of them is issued relative to this descriptor, not re-resolved from the
    name.

    Returns an open dirfd the caller must close, or None when the path leaves the
    declared surface or any ancestor component is a symlink.
    """
    for root in ROOTS:
        try:
            root_resolved = root.resolve()
            relative = target.relative_to(root_resolved)
        except (ValueError, OSError):
            continue
        # O_NOFOLLOW on the ROOT too. Protecting the component descent while opening
        # the root itself by name left the whole confinement defeatable in one move:
        # renaming the root and dropping a symlink to an outside directory in its
        # place redirected the repair off the surface entirely (review 2026-08-09, P1
        # — race_fired=True, outside_repaired=True, inside_untouched=True). The
        # descent is only as trustworthy as the descriptor it starts from.
        # Snapshot the root's identity BEFORE reopening it. Comparing fstat(dfd) with a
        # stat() taken afterwards proved nothing: a root replaced by an ordinary
        # directory before the open is observed identically by both, so the check
        # agreed with itself and the repair rewrote a hooks.json the scan had never
        # discovered (review 2026-08-09, P1 — the previous comment here claimed this
        # case was refused, and it was not). Taking the snapshot first means a swap
        # landing at the open is a mismatch.
        #
        # What this does NOT close: a swap that happens before the snapshot. Detecting
        # that needs a descriptor for the root's PARENT, which lies outside this
        # script's declared surface — ROOTS are $HOME and $HOME/Developer.
        try:
            named = os.stat(str(root_resolved), follow_symlinks=False)
        except OSError:
            continue
        try:
            dfd = os.open(str(root_resolved),
                          os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            continue
        try:
            opened = os.fstat(dfd)
            if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
                os.close(dfd)
                continue
        except OSError:
            os.close(dfd)
            continue
        try:
            for part in relative.parts[:-1]:
                nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=dfd)
                os.close(dfd)
                dfd = nxt
            return dfd
        except OSError:
            os.close(dfd)
            return None
    return None


def find_hook_files():
    seen = set()
    for root in ROOTS:
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).parts) - base_depth
            if depth >= MAX_DEPTH:
                dirnames[:] = []
                continue
            # Never descend into these — slow and never relevant.
            dirnames[:] = [
                d
                for d in dirnames
                if d not in {"node_modules", ".git", ".next", "dist", "build"}
            ]
            if ".codex" in dirnames:
                candidate = Path(dirpath) / ".codex" / "hooks.json"
                if candidate.is_file() and candidate not in seen:
                    seen.add(candidate)
                    yield candidate


def needs_repair(cmd):
    """An unguarded prettier --write on the file-path variable."""
    if not isinstance(cmd, str):
        return False
    if "prettier" not in cmd or "CLAUDE_FILE_PATH" not in cmd:
        return False
    # Already guarded (any form that tests the variable before running).
    if "-f \"$CLAUDE_FILE_PATH\"" in cmd or "-f $CLAUDE_FILE_PATH" in cmd:
        return False
    return "--write" in cmd


def repair(path):
    # Repair the file the path actually RESOLVES to. `tmp.replace(path)` swaps the
    # symlink itself for a regular file, so the link got a guarded copy, the script
    # printed success, and the canonical file every other tool reads stayed
    # unguarded — a false green. Reproduced 2026-08-08:
    #     link is still a symlink : False
    #     link command guarded    : True     <- reported success
    #     CANONICAL still UNGUARDED: True    <- the actual defect
    # Resolving first fixes the real file and leaves the link a link.
    target = path.resolve()

    # ...but a link may point ANYWHERE. Resolving without this check let a hooks.json
    # symlinked to ../outside-root.json be rewritten outside the declared depth-3 scan
    # surface (review 2026-08-09: outside_target_repaired=True,
    # target_within_scan_root=False). This script's mandate is what find_hook_files
    # scans; writing beyond it is not a repair, it is an unannounced edit.
    if not _within_scan_roots(target):
        print(f"note: {path} resolves outside the scan roots ({target}); left untouched")
        return 0

    # Pin the parent DIRECTORY, not its name. Everything below is issued relative to
    # this descriptor so that an ancestor swapped after the check above cannot move
    # the operation off the confined surface.
    dfd = _confined_parent_fd(target)
    if dfd is None:
        print(f"note: {target} could not be opened inside a scan root "
              f"(symlinked ancestor or vanished); left untouched")
        return 0
    try:
        return _repair_confined(path, target, dfd)
    finally:
        os.close(dfd)


def _repair_confined(path, target, dfd):
    name = target.name
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
    except OSError as err:
        print(f"note: {target} could not be opened, left untouched ({err})")
        return 0
    try:
        with os.fdopen(fd, "rb") as fh:
            raw = fh.read()
            # The mode is read from the OPEN descriptor, so it describes the same
            # inode the content came from.
            mode = stat.S_IMODE(os.fstat(fh.fileno()).st_mode)
    except OSError as err:
        print(f"note: {target} could not be read, left untouched ({err})")
        return 0
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as err:
        print(f"note: {target} did not parse, left untouched ({err})")
        return 0
    # Identity is the CONTENT we read, not its metadata. An (mtime_ns, size) snapshot
    # was defeated two ways: a writer landing between read and stat was never seen at
    # all, and a writer that restored the original mtime went undetected even when the
    # bytes changed. A hash of what we actually parsed cannot be spoofed by touching
    # timestamps.
    pre_digest = hashlib.sha256(raw).hexdigest()
    changed = 0
    # Every level is shape-checked. A hooks.json can be VALID JSON and still not match
    # the schema — an entry that is a string made `(entry or {}).get` raise
    # AttributeError, which aborted the entire scan (Codex P1 #2, reproduced
    # 2026-08-08). Skipping a malformed entry is right: this script's job is to remove
    # one specific defect, not to validate someone else's hooks file.
    hooks_root = data.get("hooks") if isinstance(data, dict) else None
    for event, entries in (hooks_root or {}).items() if isinstance(hooks_root, dict) else ():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                if needs_repair(hook.get("command")):
                    hook["command"] = GUARDED
                    changed += 1
    if not changed:
        return 0
    # Write via a temp file beside the target, then replace, so an interrupted write
    # cannot leave a malformed hooks.json — which would be ignored wholesale and
    # silently disable EVERY hook in it.
    #
    # The temp name must be UNPREDICTABLE. A fixed `hooks.json.tmp` is a name an
    # attacker (or a stale link) can pre-create as a symlink: writing then followed it
    # and destroyed an unrelated file, leaving hooks.json pointing at the victim
    # (review 2026-08-09: victim_overwritten=True, hooks_points_to_victim=True).
    # mkstemp creates with O_CREAT|O_EXCL and mode 0600, so it cannot follow a link.
    tmp_name = _create_temp(dfd)
    if tmp_name is None:
        print(f"note: could not create a temp file beside {target}; left untouched")
        return 0
    try:
        wfd = os.open(tmp_name, os.O_WRONLY | os.O_NOFOLLOW, dir_fd=dfd)
        with os.fdopen(wfd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2) + "\n")
        vfd = os.open(tmp_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
        with os.fdopen(vfd, "r", encoding="utf-8") as fh:
            json.loads(fh.read())  # parse-check before replacing

        # Re-read and compare CONTENT **and MODE**, not metadata. Losing another
        # process's edit silently disables whatever it just configured, and a metadata
        # check is defeated by a writer that restores the original mtime. The mode was
        # snapshotted before the temp existed and then applied blind, so a concurrent
        # `chmod 0644 -> 0600` was silently reverted by the swap without changing a
        # single byte of content (review 2026-08-09, P1). A permission hardening is
        # exactly as much a concurrent edit as a content change, and is declined the
        # same way.
        try:
            cfd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
            with os.fdopen(cfd, "rb") as fh:
                now_digest = hashlib.sha256(fh.read()).hexdigest()
                now_mode = stat.S_IMODE(os.fstat(fh.fileno()).st_mode)
        except OSError as err:
            print(f"note: {target} vanished mid-repair, left untouched ({err})")
            return 0
        if now_digest != pre_digest:
            print(f"note: {target} changed while being repaired — NOT overwriting; "
                  f"re-run bootstrap to retry")
            return 0
        if now_mode != mode:
            print(f"note: {target} mode changed {oct(mode)} -> {oct(now_mode)} while "
                  f"being repaired — NOT overwriting; re-run bootstrap to retry")
            return 0

        # Preserve the original mode. The rename adopts the TEMP file's permissions,
        # so 0600 and 0444 both became 0644 — the latter a permission downgrade.
        # A chmod failure must ABORT: previously it printed and swapped anyway, which
        # is the destructive half of the operation with the wrong mode attached.
        hfd = os.open(tmp_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
        try:
            os.chmod(hfd, mode)
        except OSError as err:
            print(f"note: could not preserve mode {oct(mode)} on {target} ({err}); "
                  f"NOT swapping — the file keeps its original mode and content")
            return 0
        finally:
            os.close(hfd)

        # os.rename, not os.replace: both are POSIX rename(2) with identical
        # overwrite semantics, but only rename exposes the dir_fd arguments this
        # confinement depends on (os.replace in os.supports_dir_fd is False here).
        os.rename(tmp_name, name, src_dir_fd=dfd, dst_dir_fd=dfd)
        tmp_name = None  # ownership transferred; nothing to clean up
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name, dir_fd=dfd)
            except OSError:
                pass

    print(f"repaired unguarded prettier hook: {target} ({changed} command(s))")
    return changed


def main():
    total = 0
    files = 0
    failed = 0
    # Fault-isolate PER FILE. Without this, one unexpected error aborted the whole
    # scan and the __main__ wrapper below converted that abort into exit 0 — so
    # bootstrap reported success while every file after the bad one was never even
    # looked at. Fail-open is deliberate here (a repair must never break bootstrap),
    # but SILENT fail-open was the defect. One bad file now costs exactly that file.
    for path in find_hook_files():
        files += 1
        try:
            total += repair(path)
        except Exception as err:  # noqa: BLE001 — one file must not end the scan
            failed += 1
            print(f"note: {path} could not be repaired, scan continues ({type(err).__name__}: {err})")
    if total:
        print(f"prettier-hook-guard: repaired {total} command(s) across {files} file(s)")
    if failed:
        # Loud on purpose: a skipped file is a file still carrying the defect.
        print(f"prettier-hook-guard: {failed} of {files} file(s) FAILED and were left unrepaired")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:  # never fail bootstrap
        print(f"note: prettier-hook-guard skipped ({err})")
        sys.exit(0)
