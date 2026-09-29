"""Committed content, read with every object on its path hashed against its id (round 12 P1s).

git trusts its object store: `git show`, `rev-parse <rev>:<path>` and `cat-file` serve whatever bytes sit under
an id, and refs/replace re-points ids. Here the commit, each tree down the path and the blob are fetched by id
with replacements off and rehashed, so a tampered or substituted object is refused, never followed. Every
reader of reviewed content (registry, cases, approval manifest, live fixture, writer control, quotes) uses this.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

_OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
MAX_WALK = 200_000  # commits visited by is_ancestor before it refuses


def is_oid(value) -> bool:
    return isinstance(value, str) and bool(_OID.fullmatch(value))


def _hash_ok(oid: str, kind: bytes, data: bytes) -> bool:
    algo = "sha1" if len(oid) == 40 else "sha256"
    return hashlib.new(algo, kind + b" %d\0" % len(data) + data).hexdigest() == oid


class Objects:
    """One `git cat-file --batch`; an object is returned only if its type matches and its bytes hash to its id."""

    def __init__(self, repo, env: dict | None = None):
        self._proc = subprocess.Popen(["git", "--no-replace-objects", "-C", str(repo), "cat-file", "--batch"],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      env=env)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._proc.stdin.close()
        self._proc.stdout.close()
        self._proc.wait()

    def get(self, oid: str, kind: bytes) -> bytes | None:
        if not is_oid(oid):  # a name git would resolve, or a newline that would desynchronise the batch
            return None
        self._proc.stdin.write(oid.encode() + b"\n")
        self._proc.stdin.flush()
        header = self._proc.stdout.readline().split()
        if len(header) != 3:  # "<oid> missing"
            return None
        data = self._proc.stdout.read(int(header[2]))
        self._proc.stdout.read(1)  # the newline after the content
        return data if header[1] == kind and _hash_ok(oid, kind, data) else None


def _headers(commit: bytes) -> list[tuple[bytes, bytes]]:
    head = commit.split(b"\n\n", 1)[0]
    return [tuple(line.split(b" ", 1)) for line in head.split(b"\n") if b" " in line]


def _entry(tree: bytes, name: bytes, width: int) -> tuple[bytes, str] | None:
    i = 0
    while i < len(tree):
        sp, nul = tree.index(b" ", i), tree.index(b"\0", i)
        if tree[sp + 1:nul] == name:
            return tree[i:sp], tree[nul + 1:nul + 1 + width].hex()
        i = nul + 1 + width
    return None


def resolve(repo, rev: str = "HEAD", env: dict | None = None) -> str | None:
    """The full commit id `rev` names, or None. A ref is trusted; everything read below it is checked."""
    out = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), "rev-parse", "--verify", "--quiet",
                          "--end-of-options", f"{rev}^{{commit}}"], capture_output=True, text=True, env=env)
    commit = out.stdout.strip()
    return commit if out.returncode == 0 and is_oid(commit) else None


def read(repo, path: str, commit: str, env: dict | None = None) -> tuple[str, bytes, bytes] | None:
    """(blob id, bytes, mode) of `path` in `commit`, every object on the way verified; None if absent or tampered."""
    parts = [p.encode() for p in Path(path).parts if p not in ("", ".")]
    if not parts or not is_oid(commit):
        return None
    with Objects(repo, env) as objects:
        body = objects.get(commit, b"commit")
        tree = dict(_headers(body)).get(b"tree", b"").decode() if body is not None else ""
        for i, name in enumerate(parts):
            data = objects.get(tree, b"tree")
            found = _entry(data, name, len(commit) // 2) if data is not None else None
            if found is None:  # a blob asked for as a tree fails its type check in get()
                return None
            mode, tree = found
        blob = objects.get(tree, b"blob")
    return None if blob is None else (tree, blob, mode)


def at_head(repo, path: str, env: dict | None = None) -> tuple[str, str, bytes] | None:
    """(commit, blob id, bytes) of `path` committed at HEAD, or None."""
    commit = resolve(repo, "HEAD", env)
    found = read(repo, path, commit, env) if commit else None
    return None if found is None else (commit, found[0], found[1])


def file_at_head(path: Path, env: dict | None = None) -> bytes | None:
    """Bytes of `path` as committed at HEAD of the repository containing it, or None."""
    top = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, env=env).stdout.strip()
    try:
        rel = path.resolve().relative_to(Path(top).resolve()) if top else None
    except ValueError:
        return None
    found = at_head(top, str(rel), env) if rel else None
    return found[2] if found else None


def blob(repo, oid: str, env: dict | None = None) -> bytes | None:
    with Objects(repo, env) as objects:
        return objects.get(oid, b"blob")


def is_ancestor(repo, ancestor: str, head: str, env: dict | None = None) -> bool:
    """`ancestor` is `head` or reachable from it through verified commits only (merge-base trusts parent lines)."""
    if not (is_oid(ancestor) and is_oid(head)):
        return False
    seen, todo = set(), [head]
    with Objects(repo, env) as objects:
        while todo and len(seen) < MAX_WALK:
            oid = todo.pop()
            if oid == ancestor:
                return True
            if oid in seen:
                continue
            seen.add(oid)
            body = objects.get(oid, b"commit")
            if body is None:
                return False  # a tampered or missing commit on the walk refuses rather than guesses
            todo += [v.decode() for k, v in _headers(body) if k == b"parent"]
    return False
