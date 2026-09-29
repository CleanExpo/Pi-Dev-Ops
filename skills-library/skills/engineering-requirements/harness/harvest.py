#!/usr/bin/env python3
"""Harvest r5 seat replies from agent transcripts straight to runs/, never through
the orchestrator's context. This is the fix for the bottleneck that truncated r5:
the transcripts were always on disk, and re-typing them was the only reason the
round could not finish.

Identifies each transcript by the seat-file path in its dispatch prompt, so no
agent ids are hardcoded and the dispatch prompt itself is unchanged.
"""
import json, pathlib, re, sys

TASKS = pathlib.Path(sys.argv[1])
RUNS = pathlib.Path.home() / ".claude/skills/engineering-requirements/harness/runs/r5"
SEAT_RE = re.compile(r"harness/arms/(with-method|no-method)/(eng-[a-z]+)\.md")


def texts(obj):
    """Yield every assistant text block in a transcript record."""
    if isinstance(obj, dict):
        if obj.get("type") == "text" and isinstance(obj.get("text"), str):
            yield obj["text"]
        for v in obj.values():
            yield from texts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from texts(v)


written, skipped = [], []
for f in sorted(TASKS.glob("*.output")):
    raw = f.read_text(errors="replace")
    m = SEAT_RE.search(raw)
    if not m:
        continue
    arm, seat = m.group(1), m.group(2)
    dest = RUNS / arm / f"{seat}.md"
    if dest.exists():
        skipped.append(f"{arm}/{seat}")
        continue

    blocks = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            blocks.extend(texts(json.loads(line)))
        except json.JSONDecodeError:
            continue
    # the seat's emitted artifact is its final substantial text block
    body = next((b for b in reversed(blocks) if "by: " + seat in b), None)
    if body is None:
        continue
    body = body.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    body = re.sub(r"^```yaml\n", "", body).replace("```\n", "", 1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body.strip() + "\n")
    written.append(f"{arm}/{seat}  ({len(body.splitlines())} lines)")

print("HARVESTED:")
for w in written:
    print("  +", w)
print(f"\nalready on disk (untouched): {len(skipped)}")
print(f"newly written: {len(written)}")
