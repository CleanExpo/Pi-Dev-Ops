# Grounding Primitive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one reusable source-grounding primitive (`app/server/grounding.py`) that re-fetches the primary source before each generation and gates on it, then retrofit the four highest-value degradation seams onto it.

**Architecture:** A pure-function module records a *source anchor* (back-pointer + content hash + TTL) on every derived artifact, and `reground()` re-fetches the primary source through an injectable resolver registry, verifying hash + TTL and detecting lineage cycles (the self-feeding-loop alarm). `require_grounding()` is the enforced gate: it proceeds only on `FRESH`, else raises. Retrofits call these at each seam — no new infra, no ledger.

**Tech Stack:** Python 3.11+, stdlib only (`hashlib`, `re`, `datetime`, `dataclasses`); `pytest` for tests; reuses existing `app/server/tao_context_mode._sha256_hex` pattern, `scripts/plaud_actions` frontmatter helpers, `swarm/pm_scoper._linear_gql`.

**Spec:** `docs/superpowers/specs/2026-06-21-grounding-primitive-design.md`

## Global Constraints

- Functions < 40 lines; files < 300 lines (extract when exceeding).
- Python: snake_case, type hints on all functions, `log = logging.getLogger(__name__)`.
- Module location is `app/server/grounding.py` (verified reachable from `scripts/`, `swarm/`, `app/server/`; do not place in `src/tao/`).
- Enforced gate: anything but `FRESH` blocks unless `allow_ungrounded=True` (which logs a warning).
- No secrets in code; resolvers needing env (`LINEAR_API_KEY`) read it at call time, never at import.
- Pure functions; all network/disk access goes through the injectable resolver registry so tests run with **no network and no real disk dependency** (resolvers mocked or pointed at `tmp_path`).
- Commits: Conventional Commits. Branch already in use: `codex/pi-ceo-health-hardening` (work here unless told otherwise).
- Status constants are the exact strings `FRESH`, `DRIFTED`, `STALE`, `MISSING`, `CYCLE`.
- Run tests from repo root with `pythonpath = ["."]` already set in `pyproject.toml`.

---

## File Structure

- **Create** `app/server/grounding.py` — the primitive (anchor record/serialize, resolver registry, reground, gate). One responsibility: source grounding.
- **Create** `tests/test_grounding.py` — full unit coverage, resolvers mocked / `tmp_path`.
- **Modify** `swarm/pm_scoper.py` — re-ground tickets to the Plaud transcript before the Gemini call; add provenance to training traces.
- **Modify** `scripts/plaud_actions.py` — embed a structured anchor in each Linear ticket body.
- **Modify** `app/server/tao_codebase_wiki.py` — re-ground wiki generation against source files; cycle-detect wiki-on-wiki.
- **Modify** `app/server/agents/board_meeting.py` — TTL-gate `prior_deep_research` re-feed.

Retrofit order follows the spec: pm_scoper → plaud_actions → codebase_wiki → board_meeting. pm_scoper handles a prose-link fallback so it delivers value on existing tickets before plaud_actions lands structured anchors.

---

## Task 1: Module scaffold — statuses, result type, `record()`

**Files:**
- Create: `app/server/grounding.py`
- Test: `tests/test_grounding.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - constants `FRESH, DRIFTED, STALE, MISSING, CYCLE: str`; `DEFAULT_TTL_HOURS: int = 168`
  - `class GroundingError(Exception)`
  - `@dataclass GroundResult(status: str, primary_text: str|None=None, primary_uri: str|None=None, chain: list[str]=[], detail: str="")`
  - `_sha256_hex(data: bytes) -> str`
  - `_utcnow() -> datetime` (tz-aware UTC)
  - `record(*, primary_source: str, derived_from: str|list[str], parent_text: str, ttl_hours: int=DEFAULT_TTL_HOURS, confidence: float|None=None, parent_chain: list[str]|None=None) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grounding.py
from datetime import datetime
from app.server import grounding


def test_record_builds_anchor_with_hash_and_timestamp():
    anchor = grounding.record(
        primary_source="brain/plaud/itr.md",
        derived_from="linear://RA-512",
        parent_text="ticket body text",
        ttl_hours=24,
        confidence=0.8,
        parent_chain=["brain/plaud/itr.md"],
    )
    assert anchor["primary_source"] == "brain/plaud/itr.md"
    assert anchor["derived_from"] == "linear://RA-512"
    assert anchor["source_sha256"] == grounding._sha256_hex(b"ticket body text")
    assert anchor["ttl_hours"] == 24
    assert anchor["confidence"] == 0.8
    # chain accumulates parent lineage + this hop's immediate parent
    assert anchor["chain"] == ["brain/plaud/itr.md", "linear://RA-512"]
    # derived_at parses as ISO and is tz-aware
    ts = datetime.fromisoformat(anchor["derived_at"])
    assert ts.tzinfo is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounding.py::test_record_builds_anchor_with_hash_and_timestamp -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.server.grounding'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/server/grounding.py
"""app/server/grounding.py — source-grounding primitive.

Stops generation-on-generation degradation: every derived artifact carries a
source anchor (back-pointer + content hash + TTL); reground() re-fetches the
primary source before the next generation, verifying hash + TTL and detecting
lineage cycles (the self-feeding-loop alarm). require_grounding() is the
enforced gate.

Pure functions; resolvers are injectable for tests. Spec:
docs/superpowers/specs/2026-06-21-grounding-primitive-design.md
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger(__name__)

FRESH = "FRESH"
DRIFTED = "DRIFTED"
STALE = "STALE"
MISSING = "MISSING"
CYCLE = "CYCLE"

DEFAULT_TTL_HOURS = 168


class GroundingError(Exception):
    """Raised by require_grounding when an artifact is not FRESH."""


@dataclass
class GroundResult:
    status: str
    primary_text: str | None = None
    primary_uri: str | None = None
    chain: list[str] = field(default_factory=list)
    detail: str = ""


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record(
    *,
    primary_source: str,
    derived_from: str | list[str],
    parent_text: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    confidence: float | None = None,
    parent_chain: list[str] | None = None,
) -> dict:
    """Build a source-anchor dict for a derived artifact.

    parent_text is the immediate parent's current content, hashed for drift
    detection. parent_chain is the parent's own lineage; the returned chain
    appends this hop's immediate parent so reground() can detect cycles. The
    caller persists the returned dict (frontmatter for markdown, fenced block
    for ticket/JSONL bodies).
    """
    first_parent = derived_from if isinstance(derived_from, str) else derived_from[0]
    anchor: dict = {
        "primary_source": primary_source,
        "derived_from": derived_from,
        "source_sha256": _sha256_hex(parent_text.encode("utf-8")),
        "derived_at": _utcnow().isoformat(),
        "ttl_hours": ttl_hours,
        "chain": list(parent_chain or []) + [first_parent],
    }
    if confidence is not None:
        anchor["confidence"] = confidence
    return anchor
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounding.py::test_record_builds_anchor_with_hash_and_timestamp -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/server/grounding.py tests/test_grounding.py
git commit -m "feat(grounding): module scaffold + record()

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Anchor serialization — `anchor_to_block` / `anchor_from_text`

**Files:**
- Modify: `app/server/grounding.py`
- Test: `tests/test_grounding.py`

**Interfaces:**
- Consumes: `record()` output dict (Task 1).
- Produces:
  - `anchor_to_block(anchor: dict) -> str` — an HTML-comment-wrapped JSON block safe to embed in a Linear ticket body (does not render).
  - `anchor_from_text(text: str) -> dict | None` — extract an anchor: first the `<!-- ground:anchor {json} -->` block; else a prose-link fallback `Source: [label](path)` → minimal anchor `{primary_source, derived_from, chain}` with no sha; else `None`.

- [ ] **Step 1: Write the failing test**

```python
def test_anchor_block_round_trips():
    anchor = grounding.record(
        primary_source="brain/plaud/itr.md",
        derived_from="linear://RA-512",
        parent_text="x",
    )
    block = grounding.anchor_to_block(anchor)
    assert block.startswith("<!-- ground:anchor")
    assert block.rstrip().endswith("-->")
    parsed = grounding.anchor_from_text("Some ticket body\n\n" + block)
    assert parsed["primary_source"] == "brain/plaud/itr.md"
    assert parsed["derived_from"] == "linear://RA-512"


def test_anchor_from_text_prose_fallback():
    body = (
        "Scan the flowchart.\n\n---\n"
        "Source: [itr.md](brain/plaud/itr.md)"
    )
    parsed = grounding.anchor_from_text(body)
    assert parsed["primary_source"] == "brain/plaud/itr.md"
    assert parsed["derived_from"] == "brain/plaud/itr.md"
    assert parsed.get("source_sha256", "") == ""  # drift unknown for legacy


def test_anchor_from_text_returns_none_when_absent():
    assert grounding.anchor_from_text("no anchor here") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounding.py -k anchor -v`
Expected: FAIL — `AttributeError: module 'app.server.grounding' has no attribute 'anchor_to_block'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/server/grounding.py` (add `import json`, `import re` at top):

```python
_ANCHOR_RE = re.compile(r"<!--\s*ground:anchor\s*(\{.*?\})\s*-->", re.DOTALL)
_SOURCE_LINK_RE = re.compile(r"Source:\s*\[[^\]]*\]\(([^)]+)\)")


def anchor_to_block(anchor: dict) -> str:
    """Serialize an anchor as an HTML comment (invisible in rendered Markdown)."""
    return f"<!-- ground:anchor {json.dumps(anchor, separators=(',', ':'))} -->"


def anchor_from_text(text: str) -> dict | None:
    """Extract an anchor from a body. Structured block wins; else prose-link
    fallback; else None."""
    m = _ANCHOR_RE.search(text or "")
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            log.warning("grounding: malformed anchor block ignored")
    link = _SOURCE_LINK_RE.search(text or "")
    if link:
        path = link.group(1).strip()
        return {"primary_source": path, "derived_from": path, "source_sha256": "", "chain": []}
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounding.py -k anchor -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/server/grounding.py tests/test_grounding.py
git commit -m "feat(grounding): anchor serialization + prose-link fallback

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Resolver registry + file resolver

**Files:**
- Modify: `app/server/grounding.py`
- Test: `tests/test_grounding.py`

**Interfaces:**
- Consumes: `_sha256_hex` (Task 1).
- Produces:
  - type alias `Resolver = Callable[[str], tuple[str, str]]` returning `(text, sha256_hex)`.
  - `_REPO_ROOT: Path` = `Path(__file__).resolve().parents[2]` (app/server/grounding.py → repo root).
  - `_scheme(uri: str) -> str` (`"file"` for repo-relative paths).
  - `default_resolvers(repo_root: Path) -> dict[str, Resolver]` — `{"file": <reads repo-relative or file:// path>}`.
  - `_resolve(uri: str, resolvers: dict[str, Resolver]) -> tuple[str, str]` (raises `KeyError` on unknown scheme).

- [ ] **Step 1: Write the failing test**

```python
def test_file_resolver_reads_and_hashes(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text("hello primary", encoding="utf-8")
    resolvers = grounding.default_resolvers(tmp_path)
    text, sha = grounding._resolve("doc.md", resolvers)
    assert text == "hello primary"
    assert sha == grounding._sha256_hex(b"hello primary")


def test_resolve_unknown_scheme_raises(tmp_path):
    resolvers = grounding.default_resolvers(tmp_path)
    import pytest
    with pytest.raises(KeyError):
        grounding._resolve("linear://RA-1", resolvers)


def test_scheme_detection():
    assert grounding._scheme("brain/plaud/x.md") == "file"
    assert grounding._scheme("file://x.md") == "file"
    assert grounding._scheme("linear://RA-9") == "linear"
    assert grounding._scheme("https://a.com") == "https"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounding.py -k "resolver or resolve or scheme" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'default_resolvers'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/server/grounding.py` (add `from pathlib import Path`, `from typing import Callable`):

```python
Resolver = Callable[[str], tuple[str, str]]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.\-]*)://")


def _scheme(uri: str) -> str:
    m = _SCHEME_RE.match(uri or "")
    if not m:
        return "file"
    return "file" if m.group(1) == "file" else m.group(1)


def default_resolvers(repo_root: Path) -> dict[str, Resolver]:
    def file_res(uri: str) -> tuple[str, str]:
        rel = uri[len("file://"):] if uri.startswith("file://") else uri
        data = (repo_root / rel).resolve().read_bytes()
        return data.decode("utf-8", errors="replace"), _sha256_hex(data)

    return {"file": file_res}


def _resolve(uri: str, resolvers: dict[str, Resolver]) -> tuple[str, str]:
    res = resolvers.get(_scheme(uri))
    if res is None:
        raise KeyError(f"no resolver for scheme of {uri!r}")
    return res(uri)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounding.py -k "resolver or resolve or scheme" -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app/server/grounding.py tests/test_grounding.py
git commit -m "feat(grounding): resolver registry + file resolver

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `reground()` — the five statuses

**Files:**
- Modify: `app/server/grounding.py`
- Test: `tests/test_grounding.py`

**Interfaces:**
- Consumes: `GroundResult`, `_resolve`, `default_resolvers`, `_REPO_ROOT`, `_utcnow`, statuses (Tasks 1–3).
- Produces: `reground(artifact_uri: str, anchor: dict, *, resolvers: dict[str, Resolver]|None=None, repo_root: Path|None=None) -> GroundResult`.
- Status precedence: `CYCLE` > `MISSING` (primary unresolvable) > `DRIFTED` (parent sha mismatch) > `STALE` (past TTL) > `FRESH`.

- [ ] **Step 1: Write the failing test**

```python
def _anchor_for(tmp_path, parent_text="p", ttl=168):
    return grounding.record(
        primary_source="primary.md",
        derived_from="primary.md",
        parent_text=parent_text,
        ttl_hours=ttl,
    )


def test_reground_fresh(tmp_path):
    (tmp_path / "primary.md").write_text("p", encoding="utf-8")
    anchor = _anchor_for(tmp_path, parent_text="p")
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.FRESH
    assert r.primary_text == "p"


def test_reground_drifted_when_parent_changed(tmp_path):
    (tmp_path / "primary.md").write_text("CHANGED", encoding="utf-8")
    anchor = _anchor_for(tmp_path, parent_text="original")  # sha of "original"
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.DRIFTED
    assert r.primary_text == "CHANGED"  # still returned so caller can re-derive


def test_reground_missing_when_primary_unresolvable(tmp_path):
    anchor = _anchor_for(tmp_path)  # primary.md not written
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.MISSING


def test_reground_stale_past_ttl(tmp_path):
    (tmp_path / "primary.md").write_text("p", encoding="utf-8")
    anchor = _anchor_for(tmp_path, parent_text="p", ttl=1)
    anchor["derived_at"] = "2000-01-01T00:00:00+00:00"  # ancient
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.STALE


def test_reground_cycle_when_self_sourced(tmp_path):
    (tmp_path / "WIKI.md").write_text("w", encoding="utf-8")
    anchor = grounding.record(
        primary_source="WIKI.md", derived_from="WIKI.md", parent_text="w",
    )
    r = grounding.reground("WIKI.md", anchor, repo_root=tmp_path)
    assert r.status == grounding.CYCLE


def test_reground_cycle_on_repeated_lineage(tmp_path):
    (tmp_path / "primary.md").write_text("p", encoding="utf-8")
    anchor = grounding.record(
        primary_source="primary.md", derived_from="b.md", parent_text="p",
        parent_chain=["primary.md", "b.md"],  # b.md repeats
    )
    r = grounding.reground("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.CYCLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounding.py -k reground -v`
Expected: FAIL — `AttributeError: ... has no attribute 'reground'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/server/grounding.py`:

```python
def reground(
    artifact_uri: str,
    anchor: dict,
    *,
    resolvers: dict[str, Resolver] | None = None,
    repo_root: Path | None = None,
) -> GroundResult:
    """Re-fetch the primary source for a derived artifact and classify it.

    Returns a GroundResult whose status is one of FRESH/DRIFTED/STALE/
    MISSING/CYCLE (precedence in that order of severity).
    """
    repo_root = repo_root or _REPO_ROOT
    resolvers = resolvers or default_resolvers(repo_root)
    primary = anchor.get("primary_source") or ""
    derived_from = anchor.get("derived_from") or primary
    parents = [derived_from] if isinstance(derived_from, str) else list(derived_from)
    chain = list(anchor.get("chain") or [])

    # 1. CYCLE — artifact sourced from itself, or a repeated hop in its lineage.
    if artifact_uri in ([primary] + parents + chain) or len(set(chain)) != len(chain):
        return GroundResult(CYCLE, None, primary, chain, f"lineage revisits {artifact_uri!r}")

    # 2. MISSING — primary cannot be resolved.
    try:
        primary_text, _ = _resolve(primary, resolvers)
    except Exception as exc:  # noqa: BLE001 — any resolver failure means unreachable
        return GroundResult(MISSING, None, primary, chain, f"cannot resolve {primary!r}: {exc}")

    # 3. DRIFTED — immediate parent changed since derive (skip if no recorded sha).
    recorded = anchor.get("source_sha256") or ""
    if recorded:
        try:
            _, current = _resolve(parents[0], resolvers)
        except Exception as exc:  # noqa: BLE001
            return GroundResult(MISSING, primary_text, primary, chain,
                                f"cannot resolve parent {parents[0]!r}: {exc}")
        if current != recorded:
            return GroundResult(DRIFTED, primary_text, primary, chain,
                                f"parent {parents[0]!r} changed since derive")

    # 4. STALE — past TTL.
    if _is_stale(anchor):
        return GroundResult(STALE, primary_text, primary, chain, "past ttl")

    # 5. FRESH.
    return GroundResult(FRESH, primary_text, primary, chain, "ok")


def _is_stale(anchor: dict) -> bool:
    ttl = int(anchor.get("ttl_hours") or DEFAULT_TTL_HOURS)
    derived_at = anchor.get("derived_at")
    if not derived_at or ttl <= 0:
        return False
    try:
        ts = datetime.fromisoformat(derived_at)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (_utcnow() - ts).total_seconds() / 3600 > ttl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounding.py -k reground -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add app/server/grounding.py tests/test_grounding.py
git commit -m "feat(grounding): reground() with FRESH/DRIFTED/STALE/MISSING/CYCLE

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `require_grounding()` — the enforced gate

**Files:**
- Modify: `app/server/grounding.py`
- Test: `tests/test_grounding.py`

**Interfaces:**
- Consumes: `reground`, `GroundResult`, `GroundingError`, `FRESH` (Tasks 1–4).
- Produces: `require_grounding(artifact_uri: str, anchor: dict, *, resolvers=None, repo_root=None, allow_ungrounded: bool=False) -> GroundResult`.

- [ ] **Step 1: Write the failing test**

```python
def test_require_grounding_returns_fresh(tmp_path):
    (tmp_path / "primary.md").write_text("p", encoding="utf-8")
    anchor = grounding.record(primary_source="primary.md", derived_from="primary.md", parent_text="p")
    r = grounding.require_grounding("art://1", anchor, repo_root=tmp_path)
    assert r.status == grounding.FRESH


def test_require_grounding_raises_on_missing(tmp_path):
    import pytest
    anchor = grounding.record(primary_source="primary.md", derived_from="primary.md", parent_text="p")
    with pytest.raises(grounding.GroundingError):
        grounding.require_grounding("art://1", anchor, repo_root=tmp_path)


def test_require_grounding_allow_ungrounded_downgrades(tmp_path, caplog):
    import logging
    anchor = grounding.record(primary_source="primary.md", derived_from="primary.md", parent_text="p")
    with caplog.at_level(logging.WARNING):
        r = grounding.require_grounding("art://1", anchor, repo_root=tmp_path, allow_ungrounded=True)
    assert r.status == grounding.MISSING
    assert any("ungrounded" in rec.message.lower() for rec in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_grounding.py -k require_grounding -v`
Expected: FAIL — `AttributeError: ... has no attribute 'require_grounding'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/server/grounding.py`:

```python
def require_grounding(
    artifact_uri: str,
    anchor: dict,
    *,
    resolvers: dict[str, Resolver] | None = None,
    repo_root: Path | None = None,
    allow_ungrounded: bool = False,
) -> GroundResult:
    """Gate a generation step. Returns a FRESH GroundResult or raises
    GroundingError. allow_ungrounded downgrades the failure to a logged
    warning and returns the (non-FRESH) result."""
    result = reground(artifact_uri, anchor, resolvers=resolvers, repo_root=repo_root)
    if result.status == FRESH:
        return result
    if allow_ungrounded:
        log.warning("grounding: proceeding ungrounded for %s — %s: %s",
                    artifact_uri, result.status, result.detail)
        return result
    raise GroundingError(f"{artifact_uri}: {result.status} — {result.detail}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_grounding.py -v`
Expected: PASS (all tests, ~18)

- [ ] **Step 5: Commit**

```bash
git add app/server/grounding.py tests/test_grounding.py
git commit -m "feat(grounding): require_grounding enforced gate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Retrofit `pm_scoper` — re-ground tickets to the Plaud transcript

**Files:**
- Modify: `swarm/pm_scoper.py` (extract prompt building from `_run_grounded_research:183`; add `_build_research_prompt`)
- Test: `tests/test_pm_scoper_grounding.py` (create)

**Interfaces:**
- Consumes: `app.server.grounding.anchor_from_text`, `reground` (Tasks 2,4).
- Produces: `_build_research_prompt(ticket: dict) -> str` — the Gemini prompt, with the original primary source prepended when grounding succeeds.

**Context:** Today `_run_grounded_research` builds the prompt inline at `swarm/pm_scoper.py:197-205` using only `ticket['description']` (~30 words). Extract prompt building into `_build_research_prompt`, which re-grounds: parse the anchor from the ticket body, `reground` to fetch the Plaud transcript, and prepend it. On any non-FRESH status, fall back to the description-only prompt (advisory here — pm_scoper must still run on legacy/source-less tickets), logging the status.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pm_scoper_grounding.py
from pathlib import Path
import importlib


def test_build_research_prompt_prepends_transcript(tmp_path, monkeypatch):
    from app.server import grounding
    plaud = tmp_path / "brain" / "plaud" / "itr.md"
    plaud.parent.mkdir(parents=True)
    plaud.write_text("FULL TRANSCRIPT: the ITR button referral system ...", encoding="utf-8")
    anchor = grounding.record(
        primary_source="brain/plaud/itr.md",
        derived_from="brain/plaud/itr.md",
        parent_text=plaud.read_text(),
    )
    block = grounding.anchor_to_block(anchor)

    import swarm.pm_scoper as pm
    monkeypatch.setattr(pm, "_GROUND_REPO_ROOT", tmp_path)
    ticket = {
        "identifier": "RA-512",
        "title": "Scan the flowchart",
        "description": "Scan the flowchart photo.\n\n" + block,
    }
    prompt = pm._build_research_prompt(ticket)
    assert "FULL TRANSCRIPT" in prompt
    assert "RA-512" in prompt


def test_build_research_prompt_falls_back_without_anchor(tmp_path, monkeypatch):
    import swarm.pm_scoper as pm
    monkeypatch.setattr(pm, "_GROUND_REPO_ROOT", tmp_path)
    ticket = {"identifier": "RA-1", "title": "T", "description": "no anchor here"}
    prompt = pm._build_research_prompt(ticket)
    assert "RA-1" in prompt
    assert "no anchor here" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pm_scoper_grounding.py -v`
Expected: FAIL — `AttributeError: module 'swarm.pm_scoper' has no attribute '_build_research_prompt'`

- [ ] **Step 3: Write minimal implementation**

In `swarm/pm_scoper.py`, add near the imports:

```python
from pathlib import Path as _Path

from app.server import grounding

_GROUND_REPO_ROOT = _Path(__file__).resolve().parents[1]
```

Add the prompt builder (this is the re-grounding seam):

```python
def _build_research_prompt(ticket: dict) -> str:
    """Build the Gemini spec prompt, re-grounded to the primary source.

    Parses the ticket's source anchor, re-fetches the original transcript, and
    prepends it. Falls back to description-only on any non-FRESH status — this
    seam is advisory so the scoper still runs on legacy/source-less tickets.
    """
    description = (ticket.get("description") or "(no description)").strip()
    primary_block = ""
    anchor = grounding.anchor_from_text(description)
    if anchor:
        result = grounding.reground(
            f"linear://{ticket['identifier']}", anchor, repo_root=_GROUND_REPO_ROOT,
        )
        if result.status == grounding.FRESH and result.primary_text:
            primary_block = (
                f"Original primary source ({result.primary_uri}) — "
                f"the founder's own words, authoritative over the summary below:\n"
                f"{result.primary_text}\n\n"
            )
        else:
            log.info("pm_scoper: ticket %s ungrounded (%s) — using description only",
                     ticket["identifier"], result.status)
    return (
        f"{primary_block}"
        f"Concrete specification for Linear ticket {ticket['identifier']}: "
        f"\"{ticket['title']}\".\n\n"
        f"Original ambiguous description:\n{description}\n\n"
        f"Produce: (1) the 1-paragraph problem statement in concrete terms, "
        f"(2) 3–5 acceptance criteria as bullet points, (3) the implementation "
        f"approach in 2–4 sentences, (4) any open questions that still block "
        f"shipping. Format as Markdown. Cite sources for any external facts."
    )
```

Then in `_run_grounded_research` (currently `swarm/pm_scoper.py:197-205`), replace the inline `prompt = ( ... )` assignment with:

```python
    prompt = _build_research_prompt(ticket)
```

(Leave the surrounding `try/except`, `asyncio.run(...)`, and citation handling unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pm_scoper_grounding.py -v && python -m py_compile swarm/pm_scoper.py`
Expected: PASS (2 tests); py_compile exits 0

- [ ] **Step 5: Add provenance to the training trace**

In the `hf_traces.record(...)` call (currently `swarm/pm_scoper.py:330-338`), add the primary-source pointer to `input_context` so training signal carries provenance. Change the `input_context={...}` dict to include:

```python
                    input_context={
                        "linear_identifier": ident,
                        "team_key": ticket["team"]["key"],
                        "linear_url": ticket["url"],
                        "plaud_source": (grounding.anchor_from_text(ticket.get("description") or "") or {}).get("primary_source", ""),
                    },
```

(Keep all other existing keys in that dict exactly as they are; only add the `plaud_source` line.)

- [ ] **Step 6: Verify compile + full grounding suite still green**

Run: `python -m py_compile swarm/pm_scoper.py && python -m pytest tests/test_grounding.py tests/test_pm_scoper_grounding.py -q`
Expected: py_compile exits 0; all tests PASS

- [ ] **Step 7: Commit**

```bash
git add swarm/pm_scoper.py tests/test_pm_scoper_grounding.py
git commit -m "feat(pm_scoper): re-ground tickets to Plaud transcript before spec

Reverses the summary-only fidelity collapse: the original transcript is
prepended to the Gemini prompt when grounded; description-only fallback for
legacy tickets. Training trace now carries plaud_source provenance.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Retrofit `plaud_actions` — embed a structured anchor in each ticket

**Files:**
- Modify: `scripts/plaud_actions.py` (`create_linear_tickets:207-235`)
- Test: `tests/test_plaud_actions_grounding.py` (create)

**Interfaces:**
- Consumes: `app.server.grounding.record`, `anchor_to_block`, `anchor_from_text` (Tasks 1,2).
- Produces: ticket descriptions that contain a parseable anchor whose `primary_source` is the wiki page path.

**Context:** `create_linear_tickets` builds the description with a prose `Source:` link at `scripts/plaud_actions.py:220-224`. Add a structured anchor block alongside it so downstream `reground` is reliable (not regex-on-prose). The primary source is the wiki page; `wiki_link` is relative to the wiki dir (`plaud/<file>.md`) and the on-disk primary is `brain/<wiki_link>`. Pass the page's current text for the sha. The function signature gains an optional `page_text` param (the already-read page markdown) so no extra disk read is needed.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plaud_actions_grounding.py
import importlib


def test_ticket_description_carries_resolvable_anchor(monkeypatch):
    import scripts.plaud_actions as pa
    from app.server import grounding

    captured = {}

    def fake_create_issue(*, api_key, title, description, team_id, project_id, priority):
        captured["description"] = description
        from scripts.linear_helpers import TicketRef
        return TicketRef(identifier="RA-9", url="https://linear.app/x/RA-9")

    monkeypatch.setattr(pa, "create_linear_issue", fake_create_issue)

    action = pa.Action(title="Scan", description="Scan the flowchart", priority=3)
    refs = pa.create_linear_tickets(
        actions=[action], team_id="t", project_id="p",
        wiki_link="plaud/itr.md", linear_api_key="k",
        page_text="FULL TRANSCRIPT body",
    )
    assert refs and refs[0].identifier == "RA-9"
    anchor = grounding.anchor_from_text(captured["description"])
    assert anchor is not None
    assert anchor["primary_source"] == "brain/plaud/itr.md"
    assert anchor["source_sha256"] == grounding._sha256_hex(b"FULL TRANSCRIPT body")
```

(If `Action`'s constructor differs, read `scripts/plaud_actions.py` near its `@dataclass class Action` and match the real fields — `title`, `description`, `priority` are used at `:222-233`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_plaud_actions_grounding.py -v`
Expected: FAIL — `TypeError: create_linear_tickets() got an unexpected keyword argument 'page_text'`

- [ ] **Step 3: Write minimal implementation**

In `scripts/plaud_actions.py`, add near the top imports:

```python
from app.server import grounding
```

Change `create_linear_tickets` signature to accept `page_text` and embed the anchor. Replace the `description = ( ... )` block (`:220-224`) and the signature:

```python
def create_linear_tickets(
    *,
    actions: list[Action],
    team_id: str,
    project_id: str,
    wiki_link: str,
    linear_api_key: str,
    page_text: str = "",
) -> list[TicketRef]:
    """File one Linear ticket per Action. Returns the TicketRef for each ticket
    that was created successfully. Each description carries a structured source
    anchor pointing at the originating Plaud page for downstream re-grounding."""
    primary = f"brain/{wiki_link}"
    anchor = grounding.record(
        primary_source=primary,
        derived_from=primary,
        parent_text=page_text,
    )
    anchor_block = grounding.anchor_to_block(anchor)
    refs: list[TicketRef] = []
    for action in actions:
        description = (
            f"{action.description}\n\n"
            f"---\n"
            f"Source: [{wiki_link.rsplit('/', 1)[-1]}]({wiki_link})\n"
            f"{anchor_block}"
        )
        ref = create_linear_issue(
            api_key=linear_api_key,
            title=action.title,
            description=description,
            team_id=team_id,
            project_id=project_id,
            priority=action.priority,
        )
        if ref is not None:
            refs.append(ref)
    return refs
```

Then update the **caller** in `process_page` (`scripts/plaud_actions.py:462-465`) to pass the page text it already has. Find the `create_linear_tickets(` call and add `page_text=page_md,` (the variable holding the read page markdown — confirm its name near `:414`, where `page_md = page_path.read_text()`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_plaud_actions_grounding.py -v && python -m py_compile scripts/plaud_actions.py`
Expected: PASS; py_compile exits 0

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_actions.py tests/test_plaud_actions_grounding.py
git commit -m "feat(plaud_actions): embed structured source anchor in tickets

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Retrofit `tao_codebase_wiki` — re-ground against source, kill wiki-on-wiki

**Files:**
- Modify: `app/server/tao_codebase_wiki.py` (`_read_short_context:150-161`)
- Test: `tests/test_codebase_wiki_grounding.py` (create)

**Interfaces:**
- Consumes: nothing new from grounding at runtime here — the fix is to stop feeding the prior `WIKI.md` as context and read source files instead. The cycle insight from the primitive motivates the change; the implementation is a direct context-source swap.
- Produces: `_read_short_context(repo_root, top_dir) -> str` that excludes `WIKI.md` and includes a sample of actual source files.

**Context:** `_read_short_context` reads `("SKILL.md", "README.md", "WIKI.md")` (`:153`) — feeding the previous WIKI back in is the wiki-on-wiki loop. Swap `WIKI.md` out for a sample of real source files (the primary source the wiki documents), so each regeneration is grounded in code, not its own prior prose.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_codebase_wiki_grounding.py
from app.server import tao_codebase_wiki as wiki


def test_short_context_excludes_prior_wiki_and_includes_source(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "WIKI.md").write_text("PRIOR WIKI PROSE that must not feed back", encoding="utf-8")
    (d / "README.md").write_text("readme line", encoding="utf-8")
    (d / "core.py").write_text("def primary_thing():\n    return 42\n", encoding="utf-8")

    ctx = wiki._read_short_context(str(tmp_path), "pkg")
    assert "PRIOR WIKI PROSE" not in ctx          # no wiki-on-wiki
    assert "def primary_thing" in ctx             # grounded in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_codebase_wiki_grounding.py -v`
Expected: FAIL — assertion error: `PRIOR WIKI PROSE` still present (current code reads WIKI.md).

- [ ] **Step 3: Write minimal implementation**

Replace `_read_short_context` in `app/server/tao_codebase_wiki.py` (`:150-161`):

```python
def _read_short_context(repo_root: str, top_dir: str) -> str:
    """Grounding context for a directory's WIKI regeneration.

    Reads human-authored docs (SKILL.md, README.md) plus a sample of actual
    source files — NOT the prior WIKI.md. Re-grounding in source code prevents
    the wiki-on-wiki regeneration loop (each WIKI built from the last WIKI).
    """
    base = Path(repo_root) / top_dir
    parts: list[str] = []
    for name in ("SKILL.md", "README.md"):
        p = base / name
        if p.is_file():
            head = "\n".join(p.read_text(encoding="utf-8").splitlines()[:30])
            parts.append(f"# {name}\n{head}")
    # Ground in primary source: a small sample of source files in this dir.
    src_budget = 0
    for src in sorted(base.glob("*.py"))[:3]:
        head = "\n".join(src.read_text(encoding="utf-8").splitlines()[:40])
        parts.append(f"# source: {src.name}\n{head}")
        src_budget += 1
        if src_budget >= 3:
            break
    return "\n\n".join(parts)[:2500]
```

(`Path` is already imported in this module — confirm at the top; it is used at `:76`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_codebase_wiki_grounding.py -v && python -m py_compile app/server/tao_codebase_wiki.py`
Expected: PASS; py_compile exits 0

- [ ] **Step 5: Commit**

```bash
git add app/server/tao_codebase_wiki.py tests/test_codebase_wiki_grounding.py
git commit -m "fix(codebase_wiki): re-ground in source files, end wiki-on-wiki loop

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Retrofit `board_meeting` — TTL-gate stale `prior_deep_research`

**Files:**
- Modify: `app/server/agents/board_meeting.py` (the `prior_deep_research` injection, `:1116-1155`)
- Test: `tests/test_board_meeting_grounding.py` (create)

**Interfaces:**
- Consumes: the existing per-source `fetched` ISO date contract (`board_meeting.py:1073,1104`).
- Produces: `_prior_research_is_stale(prior: dict, ttl_days: int = 30) -> bool` — True when the newest cited source is older than `ttl_days`.

**Context:** `prior_deep_research` is re-fed into persona debates (`:1117,1131`) without a freshness check. Add a TTL helper using the existing `fetched` dates; gate the injection so stale research is flagged for re-verification rather than argued as fact.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_board_meeting_grounding.py
from app.server.agents import board_meeting as bm


def test_prior_research_fresh_when_recent():
    prior = {"findings": [{"sources": [{"url": "u", "fetched": "2999-01-01"}]}]}
    assert bm._prior_research_is_stale(prior, ttl_days=30) is False


def test_prior_research_stale_when_old():
    prior = {"findings": [{"sources": [{"url": "u", "fetched": "2000-01-01"}]}]}
    assert bm._prior_research_is_stale(prior, ttl_days=30) is True


def test_prior_research_stale_when_no_dates():
    prior = {"findings": [{"sources": [{"url": "u"}]}]}
    assert bm._prior_research_is_stale(prior, ttl_days=30) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_board_meeting_grounding.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_prior_research_is_stale'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/server/agents/board_meeting.py` (uses `datetime`; confirm `from datetime import datetime` or add it):

```python
def _prior_research_is_stale(prior: dict, ttl_days: int = 30) -> bool:
    """True when prior deep-research has no datable source within ttl_days.

    Uses the existing per-source `fetched` ISO date. No fetched date anywhere
    is treated as stale (cannot prove freshness — abstain toward re-verify)."""
    from datetime import datetime, timezone

    newest: datetime | None = None
    for finding in prior.get("findings", []) or []:
        for src in finding.get("sources", []) or []:
            raw = (src.get("fetched") or "").strip()
            if not raw:
                continue
            try:
                ts = datetime.fromisoformat(raw)
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if newest is None or ts > newest:
                newest = ts
    if newest is None:
        return True
    return (datetime.now(timezone.utc) - newest).days > ttl_days
```

Then guard the injection point (`:1131`, where `prior = brief["prior_deep_research"]`). After that line, annotate stale research instead of presenting it as current:

```python
        prior = brief["prior_deep_research"]
        if _prior_research_is_stale(prior):
            header = (header + "  ⚠️ STALE (>30d) — treat as a hypothesis to "
                      "re-verify against current sources, not established fact.")
            log.info("board: prior_deep_research is stale — flagged for re-verification")
```

(Keep the existing `_render_findings_block(...)` call that follows; only prepend the staleness flag to `header`. Confirm `header` is the variable passed to the render call near `:1145`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_board_meeting_grounding.py -v && python -m py_compile app/server/agents/board_meeting.py`
Expected: PASS (3 tests); py_compile exits 0

- [ ] **Step 5: Commit**

```bash
git add app/server/agents/board_meeting.py tests/test_board_meeting_grounding.py
git commit -m "feat(board_meeting): TTL-gate stale prior_deep_research

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] **Full grounding-related suite:**

Run: `python -m pytest tests/test_grounding.py tests/test_pm_scoper_grounding.py tests/test_plaud_actions_grounding.py tests/test_codebase_wiki_grounding.py tests/test_board_meeting_grounding.py -q`
Expected: all PASS

- [ ] **Import contract intact:**

Run: `python -c "from app.server.main import app; print(type(app).__name__)"`
Expected: prints `FastAPI`

- [ ] **Compile all touched files:**

Run: `python -m py_compile app/server/grounding.py swarm/pm_scoper.py scripts/plaud_actions.py app/server/tao_codebase_wiki.py app/server/agents/board_meeting.py`
Expected: exits 0

- [ ] **No regression in existing TAO context tests:**

Run: `python -m pytest tests/test_tao_context_mode.py tests/test_tao_judge.py -q`
Expected: all PASS (pre-existing pass/fail baseline unchanged)
