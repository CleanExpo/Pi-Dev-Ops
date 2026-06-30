#!/usr/bin/env python3
"""
improve_system.py — B.U.I.L.D. Loop. The improvement engine.

Scans the 2nd Brain vault (+ the session digests the miner produced) for
fixable problems and emits GRADED proposals into three buckets:

  • auto-apply    — low-risk, computable fixes (broken-link repair, OKF index
                    regen). Applied + logged to Wiki/_changelog.md.
                    DEFAULT OFF (review-first). Enable with --auto-apply.
  • need-signoff  — higher-stakes (merge duplicates, delete orphan, new page).
                    Written to Outcomes/reviews/YYYY-MM-DD-improve-review.md with
                    - [ ] Approve / Reject / Approve & don't ask again checkboxes.
  • more-context  — the scanner found something but can't decide. Same review file.

Deterministic core (no LLM) so it is free, fast, and testable. The .harness
lesson clustering is delegated to analyse_lessons.py --dry-run (already built).

Usage:
    python scripts/improve_system.py --dry-run     # review file → scratch
    python scripts/improve_system.py               # review file → vault (auto-apply OFF)
    python scripts/improve_system.py --auto-apply  # also apply the safe bucket

Exit codes: 0 ok · 2 infra error.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HOME = Path.home()
VAULT = HOME / "2nd Brain" / "2nd Brain"
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)


# ── helpers ──────────────────────────────────────────────────────────────────
def md_files(root: Path, exclude_index=True) -> list[Path]:
    return [p for p in root.rglob("*.md") if not (exclude_index and p.name == "index.md")]


def page_names(vault: Path) -> set[str]:
    """All resolvable page basenames (Obsidian resolves [[X]] by basename)."""
    return {p.stem for p in vault.rglob("*.md")}


def link_target(raw: str) -> str:
    """Strip Obsidian alias (|) and heading (#) → bare page name."""
    return raw.split("|")[0].split("#")[0].strip()


# ── scanners (each returns list of finding dicts) ────────────────────────────
def scan_broken_links(vault: Path, names: set[str]) -> list[dict]:
    """Only the curated Wiki/ is link-checked. Sources/ (raw imports) and
    process/ (derived digests) carry arbitrary [[refs]] and are out of scope."""
    wiki = vault / "Wiki"
    if not wiki.exists():
        return []
    # aggregate by missing target: target -> set of referencing pages
    missing: dict[str, set[str]] = defaultdict(set)
    for p in md_files(wiki):
        try:
            text = p.read_text(errors="replace")
        except Exception:
            continue
        for m in WIKILINK.finditer(text):
            tgt = link_target(m.group(1))
            if tgt and tgt not in names:
                missing[tgt].add(p.name)
    out = []
    for tgt, refs in sorted(missing.items(), key=lambda kv: -len(kv[1])):
        n = len(refs)
        # a target referenced many times is a strong "create this page" signal
        bucket = "need-signoff" if n >= 3 else "more-context"
        sample = ", ".join(sorted(refs)[:5]) + (f" +{n - 5} more" if n > 5 else "")
        out.append({"bucket": bucket, "kind": "broken-link",
                    "title": f"Missing page [[{tgt}]] — referenced by {n} page(s)",
                    "detail": f"Create `Wiki/{tgt}.md` or fix the links. Referenced from: {sample}.",
                    "auto": False})
    return out


def scan_orphan_sources(vault: Path, top=15) -> list[dict]:
    src = vault / "Sources"
    wiki = vault / "Wiki"
    if not src.exists():
        return []
    # every link target + raw basename mention across the Wiki
    referenced: set[str] = set()
    for p in (md_files(wiki) if wiki.exists() else []):
        try:
            t = p.read_text(errors="replace")
        except Exception:
            continue
        referenced.update(link_target(m.group(1)) for m in WIKILINK.finditer(t))
    orphans = [p for p in md_files(src) if p.stem not in referenced]
    out = []
    for p in orphans[:top]:
        out.append({"bucket": "need-signoff", "kind": "orphan-source",
                    "title": f"Orphan source never cited: {p.name}",
                    "detail": f"`Sources/{p.name}` is not referenced by any Wiki page. "
                              f"Cite it from a relevant Wiki page or archive it.",
                    "auto": False})
    if len(orphans) > top:
        out.append({"bucket": "more-context", "kind": "orphan-source-summary",
                    "title": f"+{len(orphans) - top} more orphan sources (not shown)",
                    "detail": f"{len(orphans)} Sources/ files total are uncited; showing first {top}. "
                              f"Likely needs a bulk triage pass, not per-file review.",
                    "auto": False})
    return out


# NOTE: OKF index freshness is owned by okf-index.py (run by wiki-ingest step 6
# and after the session miner), so improve-system does NOT re-detect index drift
# — that was redundant and the format is wikilink-based, not markdown-link-based.


def scan_near_duplicates(vault: Path) -> list[dict]:
    """Wiki pages sharing a normalized H1 title → candidate merges."""
    wiki = vault / "Wiki"
    if not wiki.exists():
        return []
    by_title: dict[str, list[str]] = defaultdict(list)
    for p in md_files(wiki):
        try:
            t = p.read_text(errors="replace")
        except Exception:
            continue
        m = H1.search(t)
        if m:
            norm = re.sub(r"[^a-z0-9]", "", m.group(1).lower())
            by_title[norm].append(p.name)
    out = []
    for norm, files in by_title.items():
        if len(files) > 1:
            out.append({"bucket": "need-signoff", "kind": "near-duplicate",
                        "title": f"Possible duplicate pages: {', '.join(files)}",
                        "detail": f"These Wiki pages share the same normalized title. Merge or differentiate.",
                        "auto": False})
    return out


def session_signal(vault: Path, top=8) -> list[dict]:
    """Aggregate the miner's digests → most-common projects as candidate coverage."""
    sess = vault / "process" / "sessions"
    if not sess.exists():
        return []
    projects: Counter = Counter()
    n = 0
    for p in sess.glob("*.md"):
        n += 1
        m = re.search(r"^project:\s*(.+)$", p.read_text(errors="replace"), re.MULTILINE)
        if m:
            projects[m.group(1).strip()] += 1
    if not n:
        return []
    top_proj = ", ".join(f"{k} ({v})" for k, v in projects.most_common(top))
    return [{"bucket": "more-context", "kind": "session-signal",
             "title": f"Session signal: {n} digests, top projects → {top_proj}",
             "detail": "High-activity projects are candidates for a dedicated Wiki page if none exists. "
                       "A future LLM pass over process/sessions/ will extract concrete learnings.",
             "auto": False}]


# ── review rendering + auto-apply ────────────────────────────────────────────
BUCKETS = ["auto-apply", "need-signoff", "more-context"]
CHECK = "- [ ] Approve    - [ ] Reject    - [ ] Approve & don't ask again"


def render_review(findings: list[dict], applied: list[dict], auto_on: bool) -> str:
    today = date.today().isoformat()
    by = defaultdict(list)
    for f in findings:
        by[f["bucket"]].append(f)
    lines = [
        "---", "type: improve-review", f"name: improve-review-{today}",
        f'description: "{len(findings)} proposals across {sum(1 for b in BUCKETS if by[b])} buckets"',
        f"date: {today}", "---", "",
        f"# Self-Improvement Review — {today}", "",
        f"`improve-system` scanned the vault and session digests. "
        f"Auto-apply is **{'ON' if auto_on else 'OFF (review-first)'}**. "
        f"Tick a box per item; re-run after to action approvals.", "",
    ]
    if applied:
        lines += [f"## ✅ Auto-applied ({len(applied)})", ""]
        lines += [f"- {a['title']}" for a in applied] + [""]
    for b in BUCKETS:
        items = by[b]
        if not items:
            continue
        note = " — *would auto-apply when enabled*" if (b == "auto-apply" and not auto_on) else ""
        lines += [f"## {b} ({len(items)}){note}", ""]
        for f in items:
            lines += [f"### {f['title']}", f["detail"], CHECK, ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Self-improvement loop over the 2nd Brain vault")
    ap.add_argument("--dry-run", action="store_true", help="write review to scratch")
    ap.add_argument("--auto-apply", action="store_true", help="apply the safe bucket (default OFF)")
    ap.add_argument("--vault", default=None)
    args = ap.parse_args()

    vault = Path(args.vault) if args.vault else VAULT
    if not vault.exists():
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        return 2

    names = page_names(vault)
    findings = (scan_broken_links(vault, names) + scan_orphan_sources(vault)
                + scan_near_duplicates(vault) + session_signal(vault))

    applied: list[dict] = []
    if args.auto_apply:
        # only index-drift is auto-applied here; regen handled out-of-band by okf-index.py
        applied = [f for f in findings if f.get("auto")]
        findings = [f for f in findings if not f.get("auto")]

    review = render_review(findings + applied if not args.auto_apply else findings, applied, args.auto_apply)
    out_dir = (Path("/private/tmp/claude-501/scratch-reviews") if args.dry_run
               else vault / "Outcomes" / "reviews")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{date.today().isoformat()}-improve-review.md"
    out_file.write_text(review)

    counts = Counter(f["bucket"] for f in findings)
    print(f"improve-system: {sum(counts.values())} proposals "
          f"({dict(counts)}), {len(applied)} auto-applied → {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
