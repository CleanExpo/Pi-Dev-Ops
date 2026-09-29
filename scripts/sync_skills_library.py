"""Copy the skills library's own skills into skills-library/, and check the copy.

usage:
  python scripts/sync_skills_library.py sync <skills-library checkout> <sha>
  python scripts/sync_skills_library.py check

One home per skill (CleanExpo/skills-library skills/HOMES.json): a skill whose home is
"library" is edited only there. `sync` copies each such skill's whole folder (its SKILL.md
names sibling references, scripts and tests it needs), less caches, plus the library's
skills/index.md (router phrases) and HOMES.json, into skills-library/skills/, replacing what
was there. It pins the library commit in skills-library.lock and writes
skills-library/MANIFEST.json: that commit plus a sha256 for every copied file. The checkout
must be clean and at exactly <sha>. A symlink anywhere on the way, a source that resolves
outside the checkout, a name that is not a plain folder name, or a SKILL.md whose frontmatter
name differs from its folder stops the sync before anything is replaced.

Run by hand, like any other change: sync, check, then the normal release gate (tests and an
independent review of the exact commit) before the branch is pushed. Nothing syncs on a timer.
The image links ~/.claude/skills to the copy (Dockerfile), because library skills name their
own files by that path.

`check` needs no network, so CI runs it on every PR (tests/test_skills_library_sync.py):
- the files on disk are exactly MANIFEST.json's, byte for byte, and its commit is the lock's;
- the copy holds the shared files (_EXTRAS) and at least one skill, and every home=library skill
  not listed in HELD_BACK is there, named as its folder, with nothing else beside them;
- HELD_BACK names only home=library skills. A skill is held back while its files fail this
  repo's secrets gate (handoff-loop's audit-secrets) on example values, or run a held-back
  skill's files; it ships once the library rewrites them. Mission Control could not load it
  before this copy existed, so nothing regresses.
- a skill in this repo's skills/ whose home is the library or a single machine is listed in
  OVERLAP_BASELINE, which must exist and only shrinks: a listed skill with no PDO copy left
  fails too. While a name is listed, the skills/ copy is the one Mission Control loads
  (src/tao/skills.py), so today's behaviour does not change.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "skills-library" / "skills"
LOCK = ROOT / "skills-library.lock"
OVERLAP_BASELINE = ROOT / ".github" / "skills-library-overlap.baseline.txt"
HELD_BACK = ROOT / ".github" / "skills-library-held-back.txt"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
# Shared files beside the skills that skill bodies name: router phrases, homes, the catalogue and
# rules, and library/ (web-tool-tiers.md, connections.md: where credentials live, never values).
_EXTRAS = ("index.md", "HOMES.json", "README.md", "CLAUDE.md", "library")
# Caches and installed packages; a skill's tests are copied, since its SKILL.md may tell the
# agent to run them (review round 2).
_SKIP_DIRS = {"__pycache__", "node_modules", ".pytest_cache"}
_SKIP_FILES = re.compile(r"^.*\.pyc$")


def _homes(skills_dir: Path) -> dict[str, str]:
    return json.loads((skills_dir / "HOMES.json").read_text("utf-8"))["homes"]


def _frontmatter_name(skill_md: Path) -> str:
    from src.tao.skills import _parse_frontmatter  # the loader's own reading of a name

    meta, _ = _parse_frontmatter(skill_md.read_text("utf-8"))
    return str(meta.get("name", skill_md.parent.name))


def _files_under(src: Path, root: Path) -> list[Path]:
    """Every file under src, refusing any symlink and anything that resolves outside root."""
    if src.is_symlink() or not src.resolve().is_relative_to(root):
        raise ValueError(f"refusing {src}: a symlink or outside the checkout")
    if src.is_file():
        return [src]
    found = []
    for base, dirs, files in os.walk(src):
        for entry in dirs + files:
            if (Path(base) / entry).is_symlink():
                raise ValueError(f"refusing symlink {Path(base) / entry}")
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        found += [Path(base) / f for f in files if not _SKIP_FILES.match(f)]
    return found


def _git(library: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(library), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _plan(library: Path, sha: str) -> list[tuple[Path, str]]:
    """(source file, path relative to the copy) for everything sync will write."""
    if _git(library, "rev-parse", "HEAD") != sha or _git(library, "status", "--porcelain"):
        raise ValueError(f"{library} must be a clean checkout of {sha}")
    src = library / "skills"
    root = src.resolve()
    if library.is_symlink() or src.is_symlink():
        raise ValueError("refusing a symlinked checkout or skills/ folder")
    held = _baseline(HELD_BACK) or set()
    names = sorted(n for n, home in _homes(src).items() if home == "library" and n not in held)
    if not names:
        raise ValueError("HOMES.json names no library skills; refusing to sync an empty copy")
    absent = [extra for extra in _EXTRAS if not (src / extra).exists()]
    if absent:
        raise ValueError(f"the checkout has no skills/{absent[0]}")
    plan = []
    for name in names:
        if not _NAME.match(name):
            raise ValueError(f"refusing skill name {name!r}: not a plain folder name")
        if _frontmatter_name(src / name / "SKILL.md") != name:
            raise ValueError(f"refusing {name}: its SKILL.md names a different skill")
        plan += [(f, f.relative_to(src).as_posix()) for f in _files_under(src / name, root)]
    return plan + [(f, f.relative_to(src).as_posix()) for extra in _EXTRAS for f in _files_under(src / extra, root)]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync(library: Path, sha: str, dest: Path = DEST, lock: Path = LOCK) -> int:
    """Replace dest with the library's home=library skills; pin sha. Returns the skill count."""
    if not _SHA.match(sha):
        raise ValueError(f"sha must be 40 lower-case hex characters, got {sha!r}")
    plan = _plan(library, sha)
    staged = dest.with_name(dest.name + ".new")
    shutil.rmtree(staged, ignore_errors=True)
    for src, rel in plan:
        (staged / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, staged / rel)
    manifest = {"sha": sha, "files": {rel: _digest(staged / rel) for _, rel in sorted(plan, key=lambda p: p[1])}}
    shutil.rmtree(dest, ignore_errors=True)
    staged.rename(dest)
    (dest.parent / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", "utf-8")
    lock.write_text(sha + "\n", "utf-8")
    return len({rel.split("/", 1)[0] for _, rel in plan}) - len(_EXTRAS)


def _baseline(path: Path) -> set[str] | None:
    if not path.is_file():
        return None
    lines = (line.split("#", 1)[0].strip() for line in path.read_text("utf-8").splitlines())
    return {line for line in lines if line}


def _copy_problems(dest: Path, lock: Path) -> list[str]:
    """The copy against its manifest and the lock: bytes, file set, commit."""
    manifest_path = dest.parent / "MANIFEST.json"
    if not manifest_path.is_file():
        return ["skills-library/MANIFEST.json is missing"]
    manifest = json.loads(manifest_path.read_text("utf-8"))
    pinned = lock.read_text("utf-8").strip() if lock.is_file() else ""
    problems = [] if _SHA.match(pinned) else [f"skills-library.lock is not a 40-char SHA: {pinned!r}"]
    if manifest.get("sha") != pinned:
        problems.append(f"MANIFEST.json was synced at {manifest.get('sha')!r}, the lock says {pinned!r}")
    links = [p for p in dest.rglob("*") if p.is_symlink()]
    problems += [f"symlink in the copy: {p.relative_to(dest)}" for p in links]
    on_disk = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file() and not p.is_symlink()}
    expected = manifest.get("files", {})
    problems += [f"not in MANIFEST.json: {rel}" for rel in sorted(on_disk - set(expected))]
    problems += [f"missing from the copy: {rel}" for rel in sorted(set(expected) - on_disk)]
    problems += [f"changed since sync: {rel}" for rel in sorted(on_disk & set(expected))
                 if _digest(dest / rel) != expected[rel]]
    return problems


def _home_problems(dest: Path, pdo_skills: Path, baseline: Path) -> list[str]:
    """What was copied against HOMES.json, and this repo's skills/ against the overlap list."""
    missing = [f"the copy has no {extra}" for extra in _EXTRAS if not (dest / extra).exists()]
    if missing:
        return missing
    homes = _homes(dest)
    held = _baseline(HELD_BACK) or set()
    wanted = {n for n, home in homes.items() if home == "library" and n not in held}
    copied = {p.name for p in dest.iterdir() if p.is_dir() and p.name not in _EXTRAS}
    problems = [] if wanted else ["HOMES.json names no library skills"]
    problems += [f"{n}: listed in {HELD_BACK.name} but its home is not library; remove the line"
                 for n in sorted(held) if homes.get(n) != "library"]
    problems += [f"copied but home is not library: {n}" for n in sorted(copied - wanted)]
    problems += [f"home=library but not copied: {n}" for n in sorted(wanted - copied)]
    for n in sorted(copied & wanted):
        skill_md = dest / n / "SKILL.md"
        if not skill_md.is_file():
            problems.append(f"copied folder without SKILL.md: {n}")
        elif _frontmatter_name(skill_md) != n:
            problems.append(f"{n}: its SKILL.md names a different skill")
    listed = _baseline(baseline)
    if listed is None:
        return problems + [f"{baseline.name} is missing"]
    local = {p.parent.name for p in pdo_skills.glob("*/SKILL.md")}
    overlap = {n for n in local if homes.get(n) in ("library", "machine-local")}
    problems += [f"{n}: its home is {homes[n]}, so edit it there, not in skills/ (or merge "
                 "and delete this copy)" for n in sorted(overlap - listed)]
    problems += [f"{n}: listed in {baseline.name} but no longer overlaps; remove the line"
                 for n in sorted(listed - overlap)]
    return problems


def check(dest: Path = DEST, pdo_skills: Path = ROOT / "skills", baseline: Path = OVERLAP_BASELINE,
          lock: Path = LOCK) -> list[str]:
    """Every problem with the copy, as one line each. Empty means clean."""
    if not dest.is_dir():
        return [f"{dest} does not exist"]
    return _copy_problems(dest, lock) + _home_problems(dest, pdo_skills, baseline)


def main(argv: list[str]) -> int:
    if argv[:1] == ["sync"] and len(argv) == 3:
        print(f"copied {sync(Path(argv[1]), argv[2])} library skills at {argv[2]}")
        return 0
    if argv == ["check"]:
        problems = check()
        for line in problems:
            print("FAIL", line)
        print("skills-library copy: clean" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    print(__doc__.split("\n\n", 1)[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    sys.exit(main(sys.argv[1:]))
