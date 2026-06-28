#!/usr/bin/env python3
"""Tests for improve_system scanners. Run: python scripts/test_improve_system.py"""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import improve_system as I  # noqa: E402

FAILS = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    if not cond:
        FAILS.append(name)


def build_vault(d: Path):
    (d / "Wiki").mkdir(parents=True)
    (d / "Sources").mkdir()
    (d / "process" / "sessions").mkdir(parents=True)
    (d / "Outcomes").mkdir()
    # a page with one good link and one broken link
    (d / "Wiki" / "alpha.md").write_text("# Alpha\nSee [[beta]] and [[ghost-page]].\nCites [[real-source]].")
    (d / "Wiki" / "beta.md").write_text("# Beta\nback to [[alpha]]")
    # duplicate H1 titles → near-duplicate
    (d / "Wiki" / "dup1.md").write_text("# Same Title\nbody one")
    (d / "Wiki" / "dup2.md").write_text("# Same Title\nbody two")
    # sources: one cited, one orphan
    (d / "Sources" / "real-source.md").write_text("# Real Source")
    (d / "Sources" / "orphan.md").write_text("# Orphan never cited")
    # OKF index with drift (claims 1 concept, folder has 4 wiki files)
    (d / "Wiki" / "index.md").write_text("<!-- okf:generated -->\n# Wiki\n- [alpha](alpha.md)")
    # session digests
    (d / "process" / "sessions" / "s1.md").write_text("---\nproject: Pi-Dev-Ops\n---\n# d")
    (d / "process" / "sessions" / "s2.md").write_text("---\nproject: Pi-Dev-Ops\n---\n# d")


with tempfile.TemporaryDirectory() as tmp:
    v = Path(tmp)
    build_vault(v)
    names = I.page_names(v)

    bl = I.scan_broken_links(v, names)
    check("broken-link finds ghost-page", any("ghost-page" in f["title"] for f in bl))
    check("broken-link ignores valid [[beta]]", not any("[[beta]]" in f["title"] for f in bl))

    orph = I.scan_orphan_sources(v)
    check("orphan finds orphan.md", any("orphan.md" in f["title"] for f in orph))
    check("orphan skips cited real-source", not any("real-source" in f["title"] for f in orph))

    dup = I.scan_near_duplicates(v)
    check("near-duplicate finds dup1/dup2", any("dup1.md" in f["title"] and "dup2.md" in f["title"] for f in dup))

    sig = I.session_signal(v)
    check("session-signal aggregates 2 digests", sig and "2 digests" in sig[0]["title"])
    check("session-signal names top project", sig and "Pi-Dev-Ops" in sig[0]["title"])

    # render: review file has buckets + checkboxes, auto-apply OFF shows 'would auto-apply'
    synthetic_auto = [{"bucket": "auto-apply", "kind": "demo", "title": "demo safe fix",
                       "detail": "x", "auto": True}]
    findings = bl + orph + dup + sig + synthetic_auto
    review = I.render_review(findings, [], auto_on=False)
    check("review has checkbox", I.CHECK in review)
    check("review marks would-auto-apply", "would auto-apply" in review)
    check("review has frontmatter", "type: improve-review" in review)
    check("review groups need-signoff", "## need-signoff" in review)

print(f"\n{'ALL PASS' if not FAILS else f'{len(FAILS)} FAILURES: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)
