#!/usr/bin/env python3
"""Stage an ACCEPTED intent.md where gstack /plan-ceo-review will read it.

    python3 stage_intent.py <intent.md | -> [--repo DIR] [--lookup-from CEO_SKILL.md]

Why this exists. /plan-ceo-review is pinned upstream code and must not be edited, but
its "Design doc check" already reads the newest ~/.gstack/projects/$SLUG/*-design-*.md
as "the problem, constraints and approach source of truth". So a Capture Intent result
reaches the CEO review by being written THERE, under the exact SLUG and BRANCH the
review computes.

Refuses (exit 1, nothing written) when:
  - the intent is not `status: accepted` (the originator has not corrected and signed it),
  - `author:` or `created:` is missing from the frontmatter (playbook step 5),
  - any of the five playbook sections is missing, empty or invisible-only,
  - the intent contains any code fence or raw HTML (fail closed - both can hide a heading),
  - the lookup snippet cannot be found in the CEO review skill (drift: fail, never guess).

After writing, it RUNS the CEO review's own lookup snippet and requires it to print
"Design doc found: <the file just written>". A newer repo DESIGN.md or docs/designs/*.md
would shadow it; that is reported as a failure rather than a silent wrong input.

Stdlib only.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_LOOKUP = Path.home() / ".claude/skills/gstack-plan-ceo-review/SKILL.md"

# The playbook template: problem, proposed outcome, affected users and systems,
# constraints, open questions (academy.claude.com ai-native-sdlc-playbook/capture-intent).
SECTIONS = (
    "Problem",
    "Proposed outcome",
    "Affected users and systems",
    "Constraints",
    "Open questions",
)


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"REFUSED: {msg}", file=sys.stderr)
    sys.exit(1)


def validate(text: str) -> str:
    """Return the intent title; exit on any gap."""
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    statuses = re.findall(r"^status:\s*(\S+)", fm.group(1), re.M) if fm else []
    if [s.strip("\"'").lower() for s in statuses] != ["accepted"]:
        fail("intent is not `status: accepted` (exactly one status line) - "
             "the originator must correct and accept it first")
    # Playbook step 5: author and timestamp join the record.
    for field in ("author", "created"):
        # Value on the SAME line: a bare `author:` must not borrow the next key as its value.
        if not re.search(rf"^{field}:[ \t]*\S", fm.group(1), re.M):
            fail(f"frontmatter is missing `{field}:` - the accepted record needs author and timestamp")

    # Fail closed on anything that can hide a heading. Four review rounds each found another
    # way to hide one (column-0 fence, <pre>/comment, <code>/<div>, indented fence), because
    # stripping hiding places is an allow-list with gaps. An intent is plain prose, so code
    # fences at any indentation and raw HTML are refused outright; nothing is stripped.
    # Everything below is checked on the BODY only: headings inside the frontmatter block
    # are YAML text, not sections (round-5 bypass).
    body_text = text[fm.end():]
    fence = re.search(r"^[ \t]*(```|~~~)", body_text, re.M)
    if fence:
        fail("code blocks are not allowed in an intent - write it as plain prose")
    # CommonMark autolinks (<scheme:...>, <user@host>) are links, not HTML.
    prose = re.sub(r"<[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*>|<[^\s<>@]+@[^\s<>@]+>", "", body_text)
    # Only an HTML block can swallow the heading lines below it, and an HTML block must START
    # a line (up to 3 spaces of indent). Mid-sentence text such as "notify <customer>",
    # "cost <AUD 500" or "a < b" cannot hide a heading - a `##` line always starts a new
    # block - so it is allowed; any line that opens with "<" + letter, "!", "/" or "?" is refused.
    html = re.search(r"^ {0,3}<[A-Za-z!/?][^\n]{0,40}", prose, re.M)
    if html:
        fail(f"raw HTML is not allowed in an intent (found {html.group(0)!r}) - use plain markdown")

    title = re.search(r"^# Intent:\s*(.+?)\s*$", body_text, re.M)
    if not title:
        fail("missing title line `# Intent: <title>`")

    headings = list(re.finditer(r"^## (.+?)\s*$", body_text, re.M))
    bodies = {}
    for i, h in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(body_text)
        bodies[h.group(1).strip().lower()] = body_text[h.end():end]
    for name in SECTIONS:
        body = bodies.get(name.lower())
        if body is None:
            fail(f"missing section `## {name}`")
        # Content means at least one letter or digit: whitespace, invisible characters,
        # &nbsp; and bare markers such as ".", "---" or "***" are not content.
        # A link-reference definition such as `[//]: # (note)` never renders, so it is not content.
        shown = re.sub(r"^[ \t]*\[[^\]\n]*\]:[^\n]*$", "", body, flags=re.M).replace("&nbsp;", "")
        if not re.search(r"[^\W_]", shown):
            fail(f"section `## {name}` is empty")
    return title.group(1)


def lookup_snippet(skill_md: Path) -> str:
    try:
        src = skill_md.read_text()
    except OSError as e:
        fail(f"cannot read CEO review skill at {skill_md}: {e}")
    m = re.search(r"\*\*Design doc check:\*\*\s*```bash\n(.*?)```", src, re.S)
    if not m or "Design doc found" not in m.group(1):
        fail(f"design-doc lookup snippet not found in {skill_md} - upstream drifted; update this script")
    return m.group(1)


def run_bash(script: str, repo: Path) -> str:
    out = subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True)
    return out.stdout.strip()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("intent", help="path to intent.md, or - for stdin")
    ap.add_argument("--repo", default=".", help="repo the CEO review will run in (default: cwd)")
    ap.add_argument("--lookup-from", default=str(DEFAULT_LOOKUP), help="CEO review SKILL.md")
    args = ap.parse_args(argv)

    text = sys.stdin.read() if args.intent == "-" else Path(args.intent).read_text()
    title = validate(text)
    repo = Path(args.repo).resolve()
    snippet = lookup_snippet(Path(args.lookup_from))

    # SLUG and BRANCH exactly as the CEO review computes them - taken from its own lines.
    assigns = [l for l in snippet.splitlines() if re.match(r"^(SLUG|BRANCH)=", l)]
    if len(assigns) != 2:
        fail("could not find the SLUG= and BRANCH= lines in the lookup snippet")
    vals = run_bash("\n".join(assigns) + '\necho "$SLUG"\necho "$BRANCH"', repo).splitlines()
    if len(vals) != 2 or not all(vals):
        fail(f"SLUG/BRANCH resolved empty in {repo}: {vals}")
    slug, branch = vals

    ts = time.strftime("%Y%m%d-%H%M%S")
    dest_dir = Path.home() / ".gstack" / "projects" / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{getpass.getuser()}-{branch}-design-{ts}.md"
    header = (
        f"<!-- Source: Capture Intent (AI-Native SDLC Stage 1). Accepted intent.md for "
        f"\"{title}\". Treat as the problem, constraints and open questions for this review. -->\n"
    )
    dest.write_text(header + text)

    # Positive control: the CEO review's own lookup must now resolve to this file.
    found = run_bash(snippet, repo)
    if found != f"Design doc found: {dest}":
        dest.unlink()
        try:
            dest_dir.rmdir()  # only succeeds if this run left it empty
        except OSError:
            pass
        if found.startswith("Design doc found: "):
            fail(f"CEO review lookup picked a different doc ({found[18:]}): a newer DESIGN.md or "
                 "docs/designs/*.md in the repo shadows the staged intent.")
        fail(f"CEO review lookup cannot see files under {dest_dir} (it printed: {found!r}). "
             "The pinned lookup does not quote its paths, so under macOS bash 3.2 a HOME containing a "
             "space breaks it; "
             "the CEO review would not read this intent either.")
    print(f"STAGED: {dest}")
    print(found)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
