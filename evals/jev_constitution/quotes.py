"""Re-derive each question's `quote_verbatim` flag from the Constitution itself.

A quote is verbatim when every fragment of it appears, in order, in its source file
at the pinned Unite-Group revision. Fragments are separated by "...", "…" or a
flattened list marker " * ", so an elided list quote still has to match word for
word. Markdown emphasis, list markers and whitespace are ignored on both sides.

    python3 -m evals.jev_constitution.quotes --repo ~/Unite-Group           # check
    python3 -m evals.jev_constitution.quotes --repo ~/Unite-Group --write   # record flags

Check mode exits 1 when any stored flag disagrees with the source.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import subprocess

from evals.jev_constitution import harness

_SPLIT = re.compile(r"\.\.\.|…| \* ")


def normalise(text: str) -> str:
    text = re.sub(r"(?m)^\s*(?:[-*]|\d+\.)\s+", " ", text)
    text = re.sub(r"[*`#>]", "", text)
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def fragments(quote: str) -> list[str]:
    return [f for f in (normalise(p) for p in _SPLIT.split(quote)) if f]


def missing_fragment(quote: str, source: str) -> str | None:
    """The first fragment not found in order in `source` (already normalised), or None."""
    pos = 0
    for frag in fragments(quote):
        at = source.find(frag, pos)
        if at < 0:
            return frag
        pos = at + len(frag)
    return None


def read_source(repo: str, rev: str, name: str) -> str:
    path = name if name == "CONSTITUTION.md" else f"docs/constitution/{name}"
    for _ in range(5):  # CONSTITUTION.md is a symlink to EPIC-000
        mode = subprocess.run(["git", "-C", repo, "ls-tree", rev, path],
                              capture_output=True, text=True, check=True).stdout.split(" ", 1)[0]
        body = subprocess.run(["git", "-C", repo, "show", f"{rev}:{path}"],
                              capture_output=True, text=True, check=True).stdout
        if mode != "120000":
            return body
        path = posixpath.normpath(posixpath.join(posixpath.dirname(path), body.strip()))
    raise ValueError(f"symlink loop at {name}")


def check(data: dict, repo: str) -> dict[str, str | None]:
    rev = re.search(r"\b([0-9a-f]{9,40})\b", data["constitution"]).group(1)
    sources: dict[str, str] = {}
    result = {}
    for q in data["questions"]:
        name = q["source"].rsplit(":", 1)[0]
        if name not in sources:
            sources[name] = normalise(read_source(repo, rev, name))
        result[q["id"]] = missing_fragment(q["quote"], sources[name])
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="a Unite-Group clone holding the pinned revision")
    p.add_argument("--write", action="store_true", help="record the derived flags in questions.json")
    args = p.parse_args(argv)
    path = harness.QUESTIONS
    data = json.loads(path.read_text())
    missing = check(data, args.repo)
    drift = [q["id"] for q in data["questions"] if bool(q.get("quote_verbatim")) != (missing[q["id"]] is None)]
    for q in data["questions"]:
        if missing[q["id"]] is not None:
            print(f"NOT VERBATIM {q['id']}: {missing[q['id']][:100]}")
    print(f"verbatim {sum(m is None for m in missing.values())}/{len(missing)}; stored flags wrong: {len(drift)}")
    if args.write:
        for q in data["questions"]:
            q["quote_verbatim"] = missing[q["id"]] is None
        path.write_text(json.dumps(data, indent=1))
        return 0
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
