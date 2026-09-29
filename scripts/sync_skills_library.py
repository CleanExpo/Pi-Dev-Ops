"""Copy the skills library's own skills into skills-library/, and check the copy.

usage:
  python scripts/sync_skills_library.py sync <skills-library checkout> <sha>
  python scripts/sync_skills_library.py check

One home per skill (CleanExpo/skills-library skills/HOMES.json): a skill whose home is
"library" is edited only there. `sync` copies each such skill's SKILL.md, plus the library's
skills/index.md (router phrases) and HOMES.json, into skills-library/skills/, replacing what
was there, and pins the library commit in skills-library.lock. Only SKILL.md is copied:
Mission Control reads nothing else from a skill, and the library's scripts and reference
trees (tens of MB) would only bloat the image. Symlinks are refused, never followed.

`check` needs no network, so CI runs it on every PR (tests/test_skills_library_sync.py):
- every copied skill is home=library in the copied HOMES.json, and every home=library skill
  was copied;
- no copied file is a symlink;
- a skill in this repo's skills/ whose home is the library or a single machine is listed in
  OVERLAP_BASELINE. That list only shrinks: a listed skill with no PDO copy left fails too.
  Until a listed skill's PDO copy is merged into the library and removed, the PDO copy is
  the one Mission Control loads (src/tao/skills.py), so today's behaviour does not change.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "skills-library" / "skills"
LOCK = ROOT / "skills-library.lock"
OVERLAP_BASELINE = ROOT / ".github" / "skills-library-overlap.baseline.txt"
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _homes(skills_dir: Path) -> dict[str, str]:
    return json.loads((skills_dir / "HOMES.json").read_text("utf-8"))["homes"]


def _copy_file(src: Path, dst: Path) -> None:
    if src.is_symlink():
        raise ValueError(f"refusing symlink {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def sync(library: Path, sha: str, dest: Path = DEST, lock: Path = LOCK) -> int:
    """Replace dest with the library's home=library SKILL.md files; pin sha. Returns the count."""
    if not _SHA.match(sha):
        raise ValueError(f"sha must be 40 lower-case hex characters, got {sha!r}")
    src = library / "skills"
    names = sorted(n for n, home in _homes(src).items() if home == "library")
    staged = dest.with_name(dest.name + ".new")
    shutil.rmtree(staged, ignore_errors=True)
    for name in names:
        _copy_file(src / name / "SKILL.md", staged / name / "SKILL.md")
    for extra in ("index.md", "HOMES.json"):
        _copy_file(src / extra, staged / extra)
    shutil.rmtree(dest, ignore_errors=True)
    staged.rename(dest)
    lock.write_text(sha + "\n", "utf-8")
    return len(names)


def _baseline(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    lines = (line.split("#", 1)[0].strip() for line in path.read_text("utf-8").splitlines())
    return {line for line in lines if line}


def check(dest: Path = DEST, pdo_skills: Path = ROOT / "skills", baseline: Path = OVERLAP_BASELINE,
          lock: Path = LOCK) -> list[str]:
    """Every problem with the copy, as one line each. Empty means clean."""
    homes = _homes(dest)
    problems = [f"symlink in the copy: {p.relative_to(dest)}" for p in dest.rglob("*") if p.is_symlink()]
    copied = {p.name for p in dest.iterdir() if p.is_dir()}
    wanted = {n for n, home in homes.items() if home == "library"}
    problems += [f"copied but home is not library: {n}" for n in sorted(copied - wanted)]
    problems += [f"home=library but not copied: {n}" for n in sorted(wanted - copied)]
    problems += [f"copied folder without SKILL.md: {n}" for n in sorted(copied) if not (dest / n / "SKILL.md").is_file()]
    local = {p.parent.name for p in pdo_skills.glob("*/SKILL.md")}
    overlap = {n for n in local if homes.get(n) in ("library", "machine-local")}
    listed = _baseline(baseline)
    problems += [f"{n}: its home is {homes[n]}, so edit it there, not in skills/ (or merge "
                 "and delete this copy)" for n in sorted(overlap - listed)]
    problems += [f"{n}: listed in {baseline.name} but no longer overlaps; remove the line"
                 for n in sorted(listed - overlap)]
    pinned = lock.read_text("utf-8").strip() if lock.is_file() else ""
    if not _SHA.match(pinned):
        problems.append(f"skills-library.lock is not a 40-char SHA: {pinned!r}")
    return problems


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
    sys.exit(main(sys.argv[1:]))
