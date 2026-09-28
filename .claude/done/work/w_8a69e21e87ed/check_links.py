"""Every relative markdown link in the PR's authored docs resolves to a file on disk.

Positive control: run with --canary to append a dead link in memory and prove the
checker reports it (exit 1).
"""
import re
import sys
from pathlib import Path

FILES = [
    "docs/plans/idea-to-live/intent.md",
    "docs/plans/idea-to-live/pathway.md",
    "docs/plans/idea-to-live/routing-reconciliation.md",
    "docs/model-fabric-mission-control.md",
    "CLAUDE.md",
]
LINK = re.compile(r"\]\(([^)\s]+)\)")


def dead_links(path: Path, text: str) -> list[str]:
    dead = []
    for target in LINK.findall(text):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        rel = target.split("#", 1)[0]
        if rel and not (path.parent / rel).exists():
            dead.append(f"{path}: {target}")
    return dead


def main() -> int:
    dead, checked = [], 0
    for name in FILES:
        p = Path(name)
        text = p.read_text()
        if "--canary" in sys.argv and name == FILES[0]:
            text += "\n[canary](./does-not-exist.md)\n"
        checked += len(LINK.findall(text))
        dead += dead_links(p, text)
    print(f"links scanned: {checked}; dead: {len(dead)}")
    for d in dead:
        print("DEAD", d)
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
