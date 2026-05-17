# Plaud → Brain ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship sub-project 1 of 3 — a 5-min-polling Hermes cron that ingests every new Plaud NotePin recording into the Brain-1 wiki and Margot's Supabase corpus, with a delete escape hatch.

**Architecture:** Single Python script (`scripts/plaud_ingest.py`) invoked every 5 min by a macOS LaunchAgent. Reads state file → calls Plaud MCP via the `mcp` Python SDK → writes one markdown page per recording under `wiki/plaud/` → kicks the existing `sync_wiki_to_supabase.py` → DMs Margot via Telegram Bot API. Source of truth: `docs/superpowers/specs/2026-05-17-plaud-brain-ingestion-design.md`.

**Tech Stack:** Python 3.11+, `mcp` Python SDK, `pytest` (already configured), `urllib.request` (stdlib HTTP — no new deps), macOS `launchd` for scheduling.

**Deviation from spec:** Spec said "Hermes cron". Hermes cron (`~/.hermes/cron/jobs.json`) runs LLM agents per tick, which would burn tokens for a deterministic script. We use macOS `launchd` (native scheduler) instead. Same 5-min cadence, no LLM cost. Spec intent is preserved.

**Module layout:**

- `scripts/plaud_ingest.py` — single file, ~280 lines, sections separated by comments. Matches existing flat layout in `scripts/`.
- `tests/test_plaud_ingest.py` — pytest, mocked MCP + Telegram. Live integration test guarded by `RUN_PLAUD_LIVE=1`.
- `scripts/delete-plaud-recording.sh` — bash escape hatch.
- `scripts/sync_wiki_to_supabase.py` — 2-line patch (existing file).
- `~/Library/LaunchAgents/com.phillmcgurk.plaud-ingest.plist` — LaunchAgent.
- `~/2nd Brain/2nd Brain/Wiki/plaud/.gitkeep` — seed the directory.
- `~/2nd Brain/2nd Brain/Wiki/index.md` — add one line under "Live ingestion".

---

## Task 0: Verify environment + Plaud auth still valid

**Files:** none (pre-flight check)

- [ ] **Step 1: Confirm Plaud auth not stale**

Run:
```bash
cat ~/.plaud/tokens-mcp.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('expires_at:', d.get('expires_at', 'unknown'))"
```
Expected: prints an `expires_at` field. If it's in the past, run `npx -y @plaud-ai/mcp@latest login` first and complete the browser OAuth. Do NOT continue until tokens are fresh.

- [ ] **Step 2: Install Python `mcp` SDK**

Run:
```bash
cd ~/Pi-CEO/Pi-Dev-Ops && pip install mcp
```
Expected: install succeeds. The SDK is published at https://pypi.org/project/mcp/.

- [ ] **Step 3: Smoke-test MCP connectivity**

Run:
```bash
python3 -c "
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    p = StdioServerParameters(command='npx', args=['-y', '@plaud-ai/mcp@latest'])
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print([t.name for t in tools.tools])

asyncio.run(main())
"
```
Expected: prints a list including `list_files`, `get_file`, `get_note`, `get_transcript`, `login`, `logout`, `get_current_user`. If `login` is required, run the login flow and retry.

- [ ] **Step 4: Confirm pyproject.toml allows new module + add `mcp` to deps**

Open `~/Pi-CEO/Pi-Dev-Ops/pyproject.toml`. Locate the `[project.dependencies]` (or equivalent) section and append:
```toml
"mcp>=1.0.0",
```
If unsure where dependencies live, run `grep -n dependencies ~/Pi-CEO/Pi-Dev-Ops/pyproject.toml` first and add to the existing list.

- [ ] **Step 5: Commit dep change**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add pyproject.toml
git commit -m "chore(deps): add mcp SDK for plaud ingester"
```

---

## Task 1: Module skeleton + slug sanitization (TDD)

**Files:**
- Create: `scripts/plaud_ingest.py`
- Create: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing slug test**

Create `tests/test_plaud_ingest.py`:
```python
"""Tests for scripts/plaud_ingest.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_ingest


def test_slug_basic():
    assert plaud_ingest.slug_from_name("Acme Q2 Pricing") == "acme-q2-pricing"


def test_slug_punctuation():
    assert plaud_ingest.slug_from_name("Acme Q2 Pricing!?") == "acme-q2-pricing"


def test_slug_unicode_folds_to_ascii():
    assert plaud_ingest.slug_from_name("Café Sync") == "cafe-sync"


def test_slug_empty_falls_back_to_id():
    assert plaud_ingest.slug_from_name("", fallback_id="abc123") == "abc123"


def test_slug_whitespace_only_falls_back():
    assert plaud_ingest.slug_from_name("   ", fallback_id="xyz") == "xyz"


def test_slug_collapses_consecutive_dashes():
    assert plaud_ingest.slug_from_name("foo --- bar") == "foo-bar"
```

- [ ] **Step 2: Run test, expect failure**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops && pytest tests/test_plaud_ingest.py -v
```
Expected: `ModuleNotFoundError: No module named 'plaud_ingest'`.

- [ ] **Step 3: Write minimal slug implementation**

Create `scripts/plaud_ingest.py`:
```python
"""Plaud → Brain ingester. Spec: docs/superpowers/specs/2026-05-17-plaud-brain-ingestion-design.md"""
import re
import unicodedata


def slug_from_name(name: str, fallback_id: str = "") -> str:
    """ASCII-fold, lowercase, replace non-alphanum with '-', collapse repeats."""
    if not name or not name.strip():
        return fallback_id
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or fallback_id
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): slug sanitization (Task 1)"
```

---

## Task 2: Transcript splitter for >50k content (TDD)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing splitter tests**

Append to `tests/test_plaud_ingest.py`:
```python
def test_splitter_no_split_under_limit():
    segments = [{"start_ms": i*1000, "end_ms": (i+1)*1000, "speaker": "A", "text": "x"*10}
                for i in range(50)]
    parts = plaud_ingest.split_segments(segments, max_chars=10_000)
    assert len(parts) == 1
    assert parts[0] == segments


def test_splitter_breaks_on_segment_boundary():
    segments = [{"start_ms": i*1000, "end_ms": (i+1)*1000, "speaker": "A", "text": "x"*1000}
                for i in range(60)]  # ~60k chars total
    parts = plaud_ingest.split_segments(segments, max_chars=20_000)
    assert len(parts) >= 3
    rebuilt = [seg for part in parts for seg in part]
    assert rebuilt == segments
    for part in parts:
        chars = sum(len(s["text"]) for s in part)
        assert chars <= 20_000 or len(part) == 1


def test_splitter_single_huge_segment_kept_intact():
    # Pathological: one segment alone exceeds limit. Don't split mid-segment.
    segments = [{"start_ms": 0, "end_ms": 60_000, "speaker": "A", "text": "x"*30_000}]
    parts = plaud_ingest.split_segments(segments, max_chars=20_000)
    assert parts == [segments]
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_plaud_ingest.py::test_splitter_no_split_under_limit -v
```
Expected: `AttributeError: module ... has no attribute 'split_segments'`.

- [ ] **Step 3: Implement splitter**

Append to `scripts/plaud_ingest.py`:
```python
def split_segments(segments: list[dict], max_chars: int = 50_000) -> list[list[dict]]:
    """Split a list of transcript segments into chunks whose total char count
    stays below max_chars. Never split a single segment. A pathological segment
    larger than max_chars is emitted as its own (oversized) part."""
    parts: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0
    for seg in segments:
        seg_chars = len(seg["text"])
        if current and current_chars + seg_chars > max_chars:
            parts.append(current)
            current = []
            current_chars = 0
        current.append(seg)
        current_chars += seg_chars
    if current:
        parts.append(current)
    return parts
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): transcript splitter for >50k content (Task 2)"
```

---

## Task 3: Frontmatter + page formatter (TDD)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing formatter tests**

Append to `tests/test_plaud_ingest.py`:
```python
def test_format_page_single_part():
    page = plaud_ingest.format_page(
        plaud_id="abc123",
        title="Acme Q2 Pricing",
        recorded_at="2026-05-17T14:32:00+10:00",
        duration_ms=720_000,
        ingested_at="2026-05-17T14:40:03+10:00",
        audio_url="https://plaud.cdn/abc.mp3",
        summary_md="## Summary\nKey decisions.",
        segments=[{"start_ms": 0, "end_ms": 5000, "speaker": "A", "text": "Hello"}],
        part=None,  # not multi-part
    )
    assert page.startswith("---\n")
    assert "type: plaud-recording" in page
    assert "plaud_id: abc123" in page
    assert "duration_human: 12m00s" in page
    assert "## Summary" in page
    assert "[00:00 - 00:05] A: Hello" in page


def test_format_page_multi_part_part_one_keeps_summary():
    page = plaud_ingest.format_page(
        plaud_id="abc123", title="Long Meeting",
        recorded_at="2026-05-17T14:00:00+10:00", duration_ms=3_600_000,
        ingested_at="2026-05-17T15:10:00+10:00", audio_url="https://plaud.cdn/abc.mp3",
        summary_md="## Summary\nKey decisions.",
        segments=[{"start_ms": 0, "end_ms": 5000, "speaker": "A", "text": "Hello"}],
        part=(1, 3),
    )
    assert "part: 1/3" in page
    assert "## Summary" in page
    assert "Key decisions." in page


def test_format_page_multi_part_part_two():
    page = plaud_ingest.format_page(
        plaud_id="abc123", title="Long Meeting",
        recorded_at="2026-05-17T14:00:00+10:00", duration_ms=3_600_000,
        ingested_at="2026-05-17T15:10:00+10:00", audio_url="https://plaud.cdn/abc.mp3",
        summary_md=None,
        segments=[{"start_ms": 1_800_000, "end_ms": 1_805_000, "speaker": "A", "text": "midway"}],
        part=(2, 3),
    )
    assert "part: 2/3" in page
    # Summary is omitted on parts 2+
    assert "## Summary" not in page
    assert "[30:00 - 30:05] A: midway" in page


def test_format_duration_human():
    assert plaud_ingest.format_duration_human(23_000) == "23s"
    assert plaud_ingest.format_duration_human(323_000) == "5m23s"
    assert plaud_ingest.format_duration_human(3_923_000) == "1h05m23s"


def test_format_timestamp():
    assert plaud_ingest.format_timestamp(0) == "00:00"
    assert plaud_ingest.format_timestamp(5_500) == "00:05"
    assert plaud_ingest.format_timestamp(125_000) == "02:05"
```

- [ ] **Step 2: Run, expect failures**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 4 new failures for `format_page`, `format_duration_human`, `format_timestamp`.

- [ ] **Step 3: Implement formatters**

Append to `scripts/plaud_ingest.py`:
```python
def format_duration_human(ms: int) -> str:
    total_s = ms // 1000
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def format_timestamp(ms: int) -> str:
    total_s = ms // 1000
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}"


def format_page(
    *,
    plaud_id: str,
    title: str,
    recorded_at: str,
    duration_ms: int,
    ingested_at: str,
    audio_url: str,
    summary_md: str | None,
    segments: list[dict],
    part: tuple[int, int] | None = None,
) -> str:
    """Render one wiki page (markdown with YAML frontmatter)."""
    fm_lines = [
        "---",
        "type: plaud-recording",
        f"plaud_id: {plaud_id}",
        f"recorded_at: {recorded_at}",
        f"duration_ms: {duration_ms}",
        f"duration_human: {format_duration_human(duration_ms)}",
        "source: plaud-notepin-s",
        f"ingested_at: {ingested_at}",
        "tags: []",
    ]
    if part is not None:
        fm_lines.append(f"part: {part[0]}/{part[1]}")
    fm_lines.append("---")

    body: list[str] = ["", f"# {title}", "", f"**Audio:** {audio_url}",
                       f"**Duration:** {format_duration_human(duration_ms)}", ""]
    if summary_md and (part is None or part[0] == 1):
        body.append(summary_md)
        body.append("")
    body.append("## Transcript")
    for seg in segments:
        start = format_timestamp(seg["start_ms"])
        end = format_timestamp(seg["end_ms"])
        speaker = seg.get("speaker", "?")
        body.append(f"[{start} - {end}] {speaker}: {seg['text']}")

    return "\n".join(fm_lines + body) + "\n"
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): wiki page formatter (Task 3)"
```

---

## Task 4: State file load/save + corruption recovery (TDD)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing state tests**

Append to `tests/test_plaud_ingest.py`:
```python
import json


def test_state_load_missing_returns_fresh(tmp_path):
    state = plaud_ingest.load_state(tmp_path / "nope.json")
    assert state["last_seen_id"] == ""
    assert state["last_seen_ts"]  # 24h ago default
    assert state["consecutive_failures"] == 0


def test_state_load_corrupt_returns_fresh_logs_warn(tmp_path, caplog):
    p = tmp_path / "state.json"
    p.write_text("{not json")
    state = plaud_ingest.load_state(p)
    assert state["last_seen_id"] == ""
    assert "corrupt" in caplog.text.lower() or "WARN" in caplog.text


def test_state_save_round_trip(tmp_path):
    p = tmp_path / "state.json"
    plaud_ingest.save_state(p, {
        "last_seen_id": "abc",
        "last_seen_ts": "2026-05-17T14:40:00+10:00",
        "last_run_status": "ok",
        "last_error": None,
        "consecutive_failures": 0,
    })
    loaded = json.loads(p.read_text())
    assert loaded["last_seen_id"] == "abc"
    assert loaded["consecutive_failures"] == 0


def test_state_save_is_atomic(tmp_path):
    """Save via tmp+rename so a crash mid-write can't corrupt the file."""
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"last_seen_id": "old"}))
    plaud_ingest.save_state(p, {"last_seen_id": "new", "last_seen_ts": "t",
                                "last_run_status": "ok", "last_error": None,
                                "consecutive_failures": 0})
    loaded = json.loads(p.read_text())
    assert loaded["last_seen_id"] == "new"
    # No stray .tmp file should remain
    assert not list(tmp_path.glob("*.tmp"))
```

- [ ] **Step 2: Run, expect failures**

```bash
pytest tests/test_plaud_ingest.py -k state -v
```
Expected: 4 failures.

- [ ] **Step 3: Implement state load/save**

Append to `scripts/plaud_ingest.py`:
```python
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("plaud_ingest")


def _iso_24h_ago() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()


def load_state(path: Path) -> dict:
    """Read state file. Missing or corrupt → fresh default (24h-ago)."""
    default = {
        "last_seen_id": "",
        "last_seen_ts": _iso_24h_ago(),
        "last_run_status": "fresh",
        "last_error": None,
        "consecutive_failures": 0,
    }
    if not path.exists():
        return default
    try:
        return {**default, **json.loads(path.read_text())}
    except (json.JSONDecodeError, OSError) as e:
        log.warning("plaud-state.json corrupt (%s); using fresh default", e)
        return default


def save_state(path: Path, state: dict) -> None:
    """Atomic write via tmp+rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, path)
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): state file load/save with corruption recovery (Task 4)"
```

---

## Task 5: PID lock with stale clearing (TDD)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing lock tests**

Append to `tests/test_plaud_ingest.py`:
```python
def test_lock_acquire_release(tmp_path):
    lockfile = tmp_path / "ingest.lock"
    with plaud_ingest.pid_lock(lockfile) as acquired:
        assert acquired is True
        assert lockfile.exists()
        assert int(lockfile.read_text().strip()) == os.getpid()
    assert not lockfile.exists()


def test_lock_blocks_when_held_by_live_pid(tmp_path):
    lockfile = tmp_path / "ingest.lock"
    # Write our own (live) PID into the file
    lockfile.write_text(str(os.getpid()))
    with plaud_ingest.pid_lock(lockfile) as acquired:
        assert acquired is False
    # Existing lock file is untouched
    assert lockfile.read_text().strip() == str(os.getpid())


def test_lock_clears_stale_dead_pid(tmp_path):
    lockfile = tmp_path / "ingest.lock"
    # PID 999999 is overwhelmingly unlikely to be a live process
    lockfile.write_text("999999")
    with plaud_ingest.pid_lock(lockfile) as acquired:
        assert acquired is True
        assert int(lockfile.read_text().strip()) == os.getpid()
```

- [ ] **Step 2: Run, expect failures**

```bash
pytest tests/test_plaud_ingest.py -k lock -v
```
Expected: 3 failures (`AttributeError: pid_lock`).

- [ ] **Step 3: Implement pid_lock**

Append to `scripts/plaud_ingest.py`:
```python
import contextlib
import errno


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as e:
        return e.errno == errno.EPERM  # process exists, no perms
    return True


@contextlib.contextmanager
def pid_lock(lockfile: Path):
    """Acquire a PID-based lock. Yields True if acquired, False if held by live PID.
    Stale (dead-PID) lock files are auto-cleared and the lock is taken."""
    acquired = False
    if lockfile.exists():
        try:
            holder = int(lockfile.read_text().strip())
            if _pid_alive(holder) and holder != os.getpid():
                yield False
                return
            else:
                log.warning("clearing stale plaud-ingest.lock from dead pid %d", holder)
        except ValueError:
            log.warning("clearing malformed plaud-ingest.lock")
    try:
        lockfile.parent.mkdir(parents=True, exist_ok=True)
        lockfile.write_text(str(os.getpid()))
        acquired = True
        yield True
    finally:
        if acquired and lockfile.exists():
            try:
                if int(lockfile.read_text().strip()) == os.getpid():
                    lockfile.unlink()
            except (ValueError, OSError):
                pass
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): pid lock with stale clearing (Task 5)"
```

---

## Task 6: Page writer with collision suffix (TDD)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plaud_ingest.py`:
```python
def test_write_page_new_file(tmp_path):
    target = plaud_ingest.write_page(tmp_path, "2026-05-17-foo", "content one")
    assert target == tmp_path / "2026-05-17-foo.md"
    assert target.read_text() == "content one"


def test_write_page_collision_appends_suffix(tmp_path):
    (tmp_path / "2026-05-17-foo.md").write_text("existing")
    target = plaud_ingest.write_page(tmp_path, "2026-05-17-foo", "content two")
    assert target == tmp_path / "2026-05-17-foo-2.md"
    assert target.read_text() == "content two"
    assert (tmp_path / "2026-05-17-foo.md").read_text() == "existing"


def test_write_page_collision_chains(tmp_path):
    (tmp_path / "2026-05-17-foo.md").write_text("a")
    (tmp_path / "2026-05-17-foo-2.md").write_text("b")
    target = plaud_ingest.write_page(tmp_path, "2026-05-17-foo", "c")
    assert target == tmp_path / "2026-05-17-foo-3.md"
```

- [ ] **Step 2: Run, expect failures**

```bash
pytest tests/test_plaud_ingest.py -k write_page -v
```
Expected: 3 failures.

- [ ] **Step 3: Implement page writer**

Append to `scripts/plaud_ingest.py`:
```python
def write_page(plaud_dir: Path, base_slug: str, content: str) -> Path:
    """Write content to {plaud_dir}/{base_slug}.md. On collision append -2, -3, …"""
    plaud_dir.mkdir(parents=True, exist_ok=True)
    target = plaud_dir / f"{base_slug}.md"
    if not target.exists():
        target.write_text(content)
        return target
    n = 2
    while True:
        target = plaud_dir / f"{base_slug}-{n}.md"
        if not target.exists():
            target.write_text(content)
            return target
        n += 1
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 24 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): page writer with collision suffix (Task 6)"
```

---

## Task 7: log.md appender + plaud/_index.md regenerator (TDD)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plaud_ingest.py`:
```python
def test_append_log_line(tmp_path):
    log_path = tmp_path / "log.md"
    log_path.write_text("# Log\n\nexisting line\n")
    plaud_ingest.append_log_line(log_path,
        "2026-05-17T14:40 | plaud-ingest | plaud/2026-05-17-foo.md | new recording (12m, 8200 chars)")
    text = log_path.read_text()
    assert "existing line" in text
    assert text.endswith("plaud/2026-05-17-foo.md | new recording (12m, 8200 chars)\n")


def test_regenerate_plaud_index_empty(tmp_path):
    plaud_dir = tmp_path / "plaud"
    plaud_dir.mkdir()
    plaud_ingest.regenerate_plaud_index(plaud_dir)
    idx = (plaud_dir / "_index.md").read_text()
    assert "# Plaud Recordings" in idx
    assert "| Date | Title | Duration | Link |" in idx


def test_regenerate_plaud_index_with_entries(tmp_path):
    plaud_dir = tmp_path / "plaud"
    plaud_dir.mkdir()
    (plaud_dir / "2026-05-17-acme-sync.md").write_text(
        "---\ntype: plaud-recording\nplaud_id: a1\nrecorded_at: 2026-05-17T14:00:00+10:00\n"
        "duration_human: 12m00s\n---\n\n# Acme Sync\n")
    (plaud_dir / "2026-05-16-other.md").write_text(
        "---\ntype: plaud-recording\nplaud_id: a2\nrecorded_at: 2026-05-16T09:00:00+10:00\n"
        "duration_human: 5m00s\n---\n\n# Other\n")
    plaud_ingest.regenerate_plaud_index(plaud_dir)
    idx = (plaud_dir / "_index.md").read_text()
    # Newest first
    assert idx.index("Acme Sync") < idx.index("Other")
    assert "12m00s" in idx
    assert "[Acme Sync](2026-05-17-acme-sync.md)" in idx


def test_regenerate_plaud_index_skips_non_plaud(tmp_path):
    plaud_dir = tmp_path / "plaud"
    plaud_dir.mkdir()
    (plaud_dir / "_index.md").write_text("old")
    (plaud_dir / "random.md").write_text("# Not a plaud recording\n")
    plaud_ingest.regenerate_plaud_index(plaud_dir)
    idx = (plaud_dir / "_index.md").read_text()
    assert "Not a plaud recording" not in idx
```

- [ ] **Step 2: Run, expect failures**

```bash
pytest tests/test_plaud_ingest.py -k "log_line or plaud_index" -v
```
Expected: 4 failures.

- [ ] **Step 3: Implement appenders**

Append to `scripts/plaud_ingest.py`:
```python
def append_log_line(log_path: Path, line: str) -> None:
    """Append one line + newline to wiki/log.md, creating the file if missing."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        if not line.endswith("\n"):
            line += "\n"
        f.write(line)


def _parse_frontmatter(text: str) -> dict | None:
    """Tiny YAML-frontmatter parser. Returns None if no frontmatter block."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    fm: dict = {}
    for raw in text[4:end].splitlines():
        if ":" not in raw:
            continue
        k, _, v = raw.partition(":")
        fm[k.strip()] = v.strip()
    return fm


def regenerate_plaud_index(plaud_dir: Path) -> None:
    """Rewrite plaud_dir/_index.md as a table of all plaud recordings, newest first."""
    rows: list[dict] = []
    for md in plaud_dir.glob("*.md"):
        if md.name == "_index.md":
            continue
        fm = _parse_frontmatter(md.read_text())
        if not fm or fm.get("type") != "plaud-recording":
            continue
        title_match = re.search(r"^#\s+(.+)$", md.read_text(), re.MULTILINE)
        title = title_match.group(1).strip() if title_match else md.stem
        rows.append({
            "recorded_at": fm.get("recorded_at", ""),
            "title": title,
            "duration_human": fm.get("duration_human", ""),
            "filename": md.name,
        })
    rows.sort(key=lambda r: r["recorded_at"], reverse=True)

    lines = ["# Plaud Recordings", "",
             "Auto-generated. Do not edit by hand. Regenerated by `plaud_ingest.py`.", "",
             "| Date | Title | Duration | Link |", "|---|---|---|---|"]
    for r in rows:
        date_short = r["recorded_at"][:10]
        lines.append(f"| {date_short} | {r['title']} | {r['duration_human']} | [{r['title']}]({r['filename']}) |")
    (plaud_dir / "_index.md").write_text("\n".join(lines) + "\n")
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 28 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): log appender + plaud/_index.md regenerator (Task 7)"
```

---

## Task 8: Telegram DM notifier (TDD)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_plaud_ingest.py`:
```python
from unittest.mock import patch, MagicMock


def test_notify_margot_posts_to_bot_api():
    with patch("plaud_ingest.urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__.return_value.status = 200
        plaud_ingest.notify_margot(
            bot_token="123:abc",
            chat_id="-100",
            text="📼 New Plaud: Acme (12m). I've added it to the brain.",
        )
        assert mock_open.called
        req = mock_open.call_args[0][0]
        assert req.full_url == "https://api.telegram.org/bot123:abc/sendMessage"
        # POST body contains chat_id and text
        body = req.data.decode()
        assert "chat_id" in body
        assert "Acme" in body


def test_notify_margot_swallows_errors(caplog):
    with patch("plaud_ingest.urllib.request.urlopen", side_effect=OSError("network down")):
        # Must not raise
        plaud_ingest.notify_margot(bot_token="t", chat_id="c", text="x")
    assert "telegram" in caplog.text.lower() or "notify" in caplog.text.lower()
```

- [ ] **Step 2: Run, expect failures**

```bash
pytest tests/test_plaud_ingest.py -k notify -v
```
Expected: 2 failures.

- [ ] **Step 3: Implement notifier**

Append to `scripts/plaud_ingest.py`:
```python
import urllib.parse
import urllib.request


def notify_margot(*, bot_token: str, chat_id: str, text: str) -> None:
    """Send a Telegram DM. Best-effort: any failure is logged and swallowed."""
    if not bot_token or not chat_id:
        log.warning("notify_margot: missing bot_token or chat_id; skipping")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status >= 400:
                log.warning("notify_margot: bot API returned %d", r.status)
    except (OSError, Exception) as e:
        log.warning("notify_margot: %s", e)
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 30 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): telegram dm notifier with swallowed errors (Task 8)"
```

---

## Task 9: PlaudClient wrapping the MCP server (TDD with mock)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

The client is a thin async wrapper around three MCP tool calls: `list_files`, `get_note`, `get_transcript`. Tests use a fake session; the real session is exercised in the live integration test (Task 17).

- [ ] **Step 1: Write failing test with fake session**

Append to `tests/test_plaud_ingest.py`:
```python
import asyncio


class _FakeContent:
    def __init__(self, text):
        self.text = text


class _FakeResult:
    def __init__(self, payload):
        self.content = [_FakeContent(json.dumps(payload))]


class _FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def initialize(self):
        pass

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return _FakeResult(self.responses.get(name, {}))


def test_plaud_client_list_files_since():
    fake = _FakeSession({"list_files": {"files": [
        {"id": "abc", "name": "Foo", "created_at": "2026-05-17T14:32:00+10:00",
         "duration": 720000},
    ]}})
    files = asyncio.run(plaud_ingest.PlaudClient(fake).list_files_since("2026-05-17"))
    assert len(files) == 1
    assert files[0]["id"] == "abc"
    assert fake.calls[0][0] == "list_files"


def test_plaud_client_get_note_and_transcript():
    fake = _FakeSession({
        "get_note": {"summary": "## Summary\nKey decisions."},
        "get_transcript": {"segments": [
            {"start_ms": 0, "end_ms": 5000, "speaker": "A", "text": "Hello"}]},
    })
    client = plaud_ingest.PlaudClient(fake)
    note = asyncio.run(client.get_note("abc"))
    transcript = asyncio.run(client.get_transcript("abc"))
    assert "Key decisions" in note
    assert transcript[0]["text"] == "Hello"
```

- [ ] **Step 2: Run, expect failures**

```bash
pytest tests/test_plaud_ingest.py -k plaud_client -v
```
Expected: 2 failures.

- [ ] **Step 3: Implement PlaudClient**

Append to `scripts/plaud_ingest.py`:
```python
import json


class PlaudClient:
    """Thin async wrapper. Takes an initialized `mcp.ClientSession` (or duck-typed
    fake in tests). The factory `connect_real()` spawns the npm MCP server."""

    def __init__(self, session):
        self.session = session

    @staticmethod
    def _payload(result) -> dict:
        """Extract JSON payload from an MCP tool result. Some tools return text
        content blocks containing JSON; some return structured content."""
        if hasattr(result, "structuredContent") and result.structuredContent:
            return result.structuredContent
        for block in getattr(result, "content", []):
            txt = getattr(block, "text", None)
            if txt:
                try:
                    return json.loads(txt)
                except json.JSONDecodeError:
                    return {"text": txt}
        return {}

    async def list_files_since(self, date_from: str) -> list[dict]:
        result = await self.session.call_tool("list_files",
                                              {"date_from": date_from, "page_size": 50})
        payload = self._payload(result)
        return payload.get("files", payload.get("items", []))

    async def get_note(self, plaud_id: str) -> str:
        result = await self.session.call_tool("get_note", {"id": plaud_id})
        payload = self._payload(result)
        return payload.get("summary") or payload.get("text") or ""

    async def get_transcript(self, plaud_id: str) -> list[dict]:
        result = await self.session.call_tool("get_transcript", {"id": plaud_id})
        payload = self._payload(result)
        return payload.get("segments", [])

    async def get_file(self, plaud_id: str) -> dict:
        result = await self.session.call_tool("get_file", {"id": plaud_id})
        return self._payload(result)
```

Also add the real connect helper at the bottom of the file:
```python
import asyncio
from contextlib import asynccontextmanager


@asynccontextmanager
async def connect_real_plaud():
    """Spawn @plaud-ai/mcp@latest via stdio and yield a PlaudClient."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command="npx", args=["-y", "@plaud-ai/mcp@latest"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield PlaudClient(session)
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 32 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): PlaudClient MCP wrapper (Task 9)"
```

---

## Task 10: Orchestrator happy path (TDD)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_plaud_ingest.py`:
```python
def test_run_once_happy_path_writes_page_and_advances_state(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    lock_path = tmp_path / "ingest.lock"
    wiki_dir = tmp_path / "Wiki"
    plaud_dir = wiki_dir / "plaud"

    fake = _FakeSession({
        "list_files": {"files": [{
            "id": "abc123",
            "name": "Acme Q2 Pricing",
            "created_at": "2026-05-17T14:32:00+10:00",
            "duration": 720_000,
            "presigned_url": "https://plaud.cdn/abc.mp3",
        }]},
        "get_note": {"summary": "## Summary\nKey decisions made."},
        "get_transcript": {"segments": [
            {"start_ms": 0, "end_ms": 5000, "speaker": "A", "text": "Hello"}]},
    })

    captured = {}
    def fake_notify(**kw):
        captured["notify"] = kw

    config = plaud_ingest.IngestConfig(
        state_path=state_path,
        lock_path=lock_path,
        wiki_dir=wiki_dir,
        plaud_dir=plaud_dir,
        bot_token="t", chat_id="c",
        run_sync_subprocess=lambda: None,
        notify_fn=fake_notify,
    )
    result = asyncio.run(plaud_ingest.run_once(plaud_ingest.PlaudClient(fake), config))

    assert result["ingested"] == 1
    assert result["status"] == "ok"
    written = list(plaud_dir.glob("*.md"))
    assert any("acme-q2-pricing" in p.name for p in written)
    # log.md was appended
    assert (wiki_dir / "log.md").exists()
    assert "plaud-ingest" in (wiki_dir / "log.md").read_text()
    # state advanced
    state = json.loads(state_path.read_text())
    assert state["last_seen_id"] == "abc123"
    assert state["consecutive_failures"] == 0
    # margot notified
    assert "Acme Q2 Pricing" in captured["notify"]["text"]


def test_run_once_idempotent_no_new_files(tmp_path):
    state_path = tmp_path / "state.json"
    save_state_initial = {
        "last_seen_id": "abc123",
        "last_seen_ts": "2026-05-17T14:32:00+10:00",
        "last_run_status": "ok", "last_error": None, "consecutive_failures": 0,
    }
    state_path.write_text(json.dumps(save_state_initial))

    fake = _FakeSession({"list_files": {"files": [{
        "id": "abc123",  # same ID as last_seen_id
        "name": "Acme Q2 Pricing",
        "created_at": "2026-05-17T14:32:00+10:00",
        "duration": 720_000,
    }]}})

    config = plaud_ingest.IngestConfig(
        state_path=state_path, lock_path=tmp_path / "lock",
        wiki_dir=tmp_path / "Wiki", plaud_dir=tmp_path / "Wiki" / "plaud",
        bot_token="", chat_id="",
        run_sync_subprocess=lambda: None, notify_fn=lambda **k: None,
    )
    result = asyncio.run(plaud_ingest.run_once(plaud_ingest.PlaudClient(fake), config))
    assert result["ingested"] == 0
    assert not list((tmp_path / "Wiki" / "plaud").glob("*.md") if (tmp_path/"Wiki"/"plaud").exists() else [])
```

- [ ] **Step 2: Run, expect failures**

```bash
pytest tests/test_plaud_ingest.py -k run_once -v
```
Expected: 2 failures (no `IngestConfig`, no `run_once`).

- [ ] **Step 3: Implement orchestrator (happy path only)**

Append to `scripts/plaud_ingest.py`:
```python
from dataclasses import dataclass
from typing import Callable


@dataclass
class IngestConfig:
    state_path: Path
    lock_path: Path
    wiki_dir: Path
    plaud_dir: Path
    bot_token: str
    chat_id: str
    run_sync_subprocess: Callable[[], None]
    notify_fn: Callable[..., None]
    max_chars_per_page: int = 50_000


async def _ingest_one(client: PlaudClient, file_meta: dict, cfg: IngestConfig,
                      now_iso: str) -> list[Path]:
    """Fetch note + transcript, render page(s), write. Returns list of written paths."""
    plaud_id = file_meta["id"]
    title = file_meta.get("name", plaud_id)
    duration_ms = int(file_meta.get("duration", 0))
    recorded_at = file_meta.get("created_at", now_iso)
    audio_url = file_meta.get("presigned_url", "")

    summary = await client.get_note(plaud_id)
    segments = await client.get_transcript(plaud_id)
    parts = split_segments(segments, cfg.max_chars_per_page)

    date_prefix = recorded_at[:10]
    base_slug = f"{date_prefix}-{slug_from_name(title, fallback_id=plaud_id)}"
    written: list[Path] = []
    for i, segs in enumerate(parts, start=1):
        part = (i, len(parts)) if len(parts) > 1 else None
        # Suffix multi-part filenames so they don't collide with each other
        slug = base_slug if i == 1 else f"{base_slug}-part{i}"
        page = format_page(
            plaud_id=plaud_id, title=title, recorded_at=recorded_at,
            duration_ms=duration_ms, ingested_at=now_iso, audio_url=audio_url,
            summary_md=summary if i == 1 else None,
            segments=segs, part=part,
        )
        written.append(write_page(cfg.plaud_dir, slug, page))
    return written


async def run_once(client: PlaudClient, cfg: IngestConfig) -> dict:
    """Single ingest tick. Returns a result dict {ingested, status, error}."""
    with pid_lock(cfg.lock_path) as acquired:
        if not acquired:
            log.info("plaud-ingest: previous run still active, skipping")
            return {"ingested": 0, "status": "locked", "error": None}

        state = load_state(cfg.state_path)
        date_from = state["last_seen_ts"][:10]
        files = await client.list_files_since(date_from)

        # Filter to strictly-newer than last_seen_ts
        last_ts = state["last_seen_ts"]
        new_files = [f for f in files if f.get("created_at", "") > last_ts]
        new_files.sort(key=lambda f: f["created_at"])

        now_iso = datetime.now(timezone.utc).astimezone().isoformat()
        ingested = 0
        for f in new_files:
            written = await _ingest_one(client, f, cfg, now_iso)
            for path in written:
                chars = path.stat().st_size
                append_log_line(
                    cfg.wiki_dir / "log.md",
                    f"{now_iso[:16]} | plaud-ingest | plaud/{path.name} | "
                    f"new recording ({format_duration_human(int(f.get('duration', 0)))}, "
                    f"{chars} chars)",
                )
            ingested += 1
            state["last_seen_id"] = f["id"]
            state["last_seen_ts"] = f["created_at"]
            cfg.notify_fn(bot_token=cfg.bot_token, chat_id=cfg.chat_id,
                          text=f"📼 New Plaud: {f.get('name', f['id'])} "
                               f"({format_duration_human(int(f.get('duration', 0)))}). "
                               "I've added it to the brain.")

        if ingested:
            regenerate_plaud_index(cfg.plaud_dir)
            try:
                cfg.run_sync_subprocess()
            except Exception as e:
                log.warning("sync_wiki_to_supabase.py failed: %s", e)

        state["last_run_status"] = "ok"
        state["last_error"] = None
        state["consecutive_failures"] = 0
        save_state(cfg.state_path, state)
        return {"ingested": ingested, "status": "ok", "error": None}
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 34 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): orchestrator happy path (Task 10)"
```

---

## Task 11: Orchestrator error paths (TDD)

**Files:**
- Modify: `scripts/plaud_ingest.py`
- Modify: `tests/test_plaud_ingest.py`

- [ ] **Step 1: Write failing tests for auth-expired, transient 500, network**

Append to `tests/test_plaud_ingest.py`:
```python
class _RaisingSession:
    def __init__(self, exc):
        self.exc = exc
    async def initialize(self):
        pass
    async def call_tool(self, name, args):
        raise self.exc


def test_run_once_auth_expired_dms_once_and_returns_status(tmp_path):
    state_path = tmp_path / "state.json"
    notifs = []
    cfg = plaud_ingest.IngestConfig(
        state_path=state_path, lock_path=tmp_path/"lock",
        wiki_dir=tmp_path/"Wiki", plaud_dir=tmp_path/"Wiki"/"plaud",
        bot_token="t", chat_id="c",
        run_sync_subprocess=lambda: None,
        notify_fn=lambda **k: notifs.append(k),
    )
    client = plaud_ingest.PlaudClient(_RaisingSession(Exception("401 Not authenticated")))
    result = asyncio.run(plaud_ingest.run_once(client, cfg))
    assert result["status"] == "auth_expired"
    assert len(notifs) == 1
    assert "expired" in notifs[0]["text"].lower() or "login" in notifs[0]["text"].lower()
    state = json.loads(state_path.read_text())
    assert state["last_run_status"] == "auth_expired"


def test_run_once_auth_expired_does_not_double_dm(tmp_path):
    """Second consecutive auth failure does not send a second DM."""
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "last_seen_id": "", "last_seen_ts": "2026-05-17T00:00:00+00:00",
        "last_run_status": "auth_expired", "last_error": "401",
        "consecutive_failures": 1,
    }))
    notifs = []
    cfg = plaud_ingest.IngestConfig(
        state_path=state_path, lock_path=tmp_path/"lock",
        wiki_dir=tmp_path/"Wiki", plaud_dir=tmp_path/"Wiki"/"plaud",
        bot_token="t", chat_id="c",
        run_sync_subprocess=lambda: None,
        notify_fn=lambda **k: notifs.append(k),
    )
    client = plaud_ingest.PlaudClient(_RaisingSession(Exception("401 Not authenticated")))
    asyncio.run(plaud_ingest.run_once(client, cfg))
    assert notifs == []


def test_run_once_network_failure_silent_first_failures(tmp_path):
    state_path = tmp_path / "state.json"
    notifs = []
    cfg = plaud_ingest.IngestConfig(
        state_path=state_path, lock_path=tmp_path/"lock",
        wiki_dir=tmp_path/"Wiki", plaud_dir=tmp_path/"Wiki"/"plaud",
        bot_token="t", chat_id="c",
        run_sync_subprocess=lambda: None,
        notify_fn=lambda **k: notifs.append(k),
    )
    client = plaud_ingest.PlaudClient(_RaisingSession(OSError("fetch failed")))
    result = asyncio.run(plaud_ingest.run_once(client, cfg))
    assert result["status"] == "network_error"
    assert notifs == []  # silent on first failure
    state = json.loads(state_path.read_text())
    assert state["consecutive_failures"] == 1


def test_run_once_network_failure_dms_after_threshold(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "last_seen_id": "", "last_seen_ts": "2026-05-17T00:00:00+00:00",
        "last_run_status": "network_error", "last_error": "fetch failed",
        "consecutive_failures": 5,  # next one is the 6th
    }))
    notifs = []
    cfg = plaud_ingest.IngestConfig(
        state_path=state_path, lock_path=tmp_path/"lock",
        wiki_dir=tmp_path/"Wiki", plaud_dir=tmp_path/"Wiki"/"plaud",
        bot_token="t", chat_id="c",
        run_sync_subprocess=lambda: None,
        notify_fn=lambda **k: notifs.append(k),
    )
    client = plaud_ingest.PlaudClient(_RaisingSession(OSError("fetch failed")))
    asyncio.run(plaud_ingest.run_once(client, cfg))
    assert len(notifs) == 1
    assert "unreachable" in notifs[0]["text"].lower() or "plaud" in notifs[0]["text"].lower()
```

- [ ] **Step 2: Run, expect failures**

```bash
pytest tests/test_plaud_ingest.py -k "auth_expired or network_failure" -v
```
Expected: 4 failures.

- [ ] **Step 3: Wrap `run_once` body in error handling**

Replace the body of `run_once` in `scripts/plaud_ingest.py` with:
```python
async def run_once(client: PlaudClient, cfg: IngestConfig) -> dict:
    """Single ingest tick. Returns {ingested, status, error}."""
    with pid_lock(cfg.lock_path) as acquired:
        if not acquired:
            log.info("plaud-ingest: previous run still active, skipping")
            return {"ingested": 0, "status": "locked", "error": None}

        state = load_state(cfg.state_path)
        now_iso = datetime.now(timezone.utc).astimezone().isoformat()
        try:
            date_from = state["last_seen_ts"][:10]
            files = await client.list_files_since(date_from)
        except Exception as e:
            return _handle_failure(e, state, cfg, now_iso)

        last_ts = state["last_seen_ts"]
        new_files = sorted(
            [f for f in files if f.get("created_at", "") > last_ts],
            key=lambda f: f["created_at"],
        )

        ingested = 0
        for f in new_files:
            try:
                written = await _ingest_one(client, f, cfg, now_iso)
            except Exception as e:
                return _handle_failure(e, state, cfg, now_iso)
            for path in written:
                chars = path.stat().st_size
                append_log_line(
                    cfg.wiki_dir / "log.md",
                    f"{now_iso[:16]} | plaud-ingest | plaud/{path.name} | "
                    f"new recording ({format_duration_human(int(f.get('duration', 0)))}, "
                    f"{chars} chars)",
                )
            ingested += 1
            state["last_seen_id"] = f["id"]
            state["last_seen_ts"] = f["created_at"]
            cfg.notify_fn(bot_token=cfg.bot_token, chat_id=cfg.chat_id,
                          text=f"📼 New Plaud: {f.get('name', f['id'])} "
                               f"({format_duration_human(int(f.get('duration', 0)))}). "
                               "I've added it to the brain.")

        if ingested:
            regenerate_plaud_index(cfg.plaud_dir)
            try:
                cfg.run_sync_subprocess()
            except Exception as e:
                log.warning("sync_wiki_to_supabase.py failed: %s", e)

        state.update({"last_run_status": "ok", "last_error": None, "consecutive_failures": 0})
        save_state(cfg.state_path, state)
        return {"ingested": ingested, "status": "ok", "error": None}


def _handle_failure(exc: Exception, state: dict, cfg: IngestConfig, now_iso: str) -> dict:
    msg = str(exc)
    is_auth = "401" in msg or "Not authenticated" in msg or "Unauthorized" in msg
    prev_failures = state.get("consecutive_failures", 0)
    state["consecutive_failures"] = prev_failures + 1
    state["last_error"] = msg

    if is_auth:
        state["last_run_status"] = "auth_expired"
        # DM once when transitioning into auth_expired
        if state.get("last_run_status") != "auth_expired" or prev_failures == 0:
            cfg.notify_fn(bot_token=cfg.bot_token, chat_id=cfg.chat_id,
                          text="⚠️ Plaud token expired — open Hermes and run `plaud login`.")
        save_state(cfg.state_path, state)
        return {"ingested": 0, "status": "auth_expired", "error": msg}

    # Network / transient
    state["last_run_status"] = "network_error"
    # Threshold: 6 consecutive failures (~30 min) → one-time DM
    if state["consecutive_failures"] == 6:
        cfg.notify_fn(bot_token=cfg.bot_token, chat_id=cfg.chat_id,
                      text="⚠️ Plaud unreachable for 30 min.")
    save_state(cfg.state_path, state)
    return {"ingested": 0, "status": "network_error", "error": msg}
```

Note: the "DM once when transitioning" logic above checks `last_run_status` BEFORE the update, but we've already mutated `state["consecutive_failures"]`. Look at the loaded state — we use `prev_failures` for the DM condition. Re-check the auth path: we want to DM only if previous status WAS NOT `auth_expired`, OR if this is the first failure. The condition `state.get("last_run_status") != "auth_expired" or prev_failures == 0` reads the loaded state (correct — we haven't overwritten `last_run_status` yet in this scope), so this works.

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 38 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/plaud_ingest.py tests/test_plaud_ingest.py
git commit -m "feat(plaud-ingest): error paths — auth, network, threshold DM (Task 11)"
```

---

## Task 12: CLI entry point + flags

**Files:**
- Modify: `scripts/plaud_ingest.py`

- [ ] **Step 1: Add CLI `main()` and argparse**

Append to `scripts/plaud_ingest.py`:
```python
import argparse
import subprocess


DEFAULT_WIKI_DIR = Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"
DEFAULT_STATE_PATH = Path.home() / ".hermes" / "plaud-state.json"
DEFAULT_LOCK_PATH = Path.home() / ".hermes" / "plaud-ingest.lock"
DEFAULT_LOG_PATH = Path.home() / ".hermes" / "logs" / "plaud-ingest.log"
SYNC_SCRIPT = Path.home() / "Pi-CEO" / "Pi-Dev-Ops" / "scripts" / "sync_wiki_to_supabase.py"


def _load_env(env_path: Path = Path.home() / ".hermes" / ".env") -> dict:
    """Parse a simple KEY=VALUE .env file. Strips quotes."""
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip("'\"")
    return env


def _configure_logging():
    DEFAULT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handler = logging.FileHandler(DEFAULT_LOG_PATH)
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _build_default_config(env: dict, *, backfill_since: str | None = None) -> IngestConfig:
    plaud_dir = DEFAULT_WIKI_DIR / "plaud"
    state_path = DEFAULT_STATE_PATH
    if backfill_since:
        # Override state so the run picks up everything since `backfill_since`
        state_path = DEFAULT_STATE_PATH.with_suffix(".backfill.json")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({
            "last_seen_id": "", "last_seen_ts": backfill_since,
            "last_run_status": "fresh", "last_error": None, "consecutive_failures": 0,
        }))

    def run_sync():
        subprocess.run(["python3", str(SYNC_SCRIPT)], check=False, timeout=120)

    return IngestConfig(
        state_path=state_path,
        lock_path=DEFAULT_LOCK_PATH,
        wiki_dir=DEFAULT_WIKI_DIR,
        plaud_dir=plaud_dir,
        bot_token=env.get("TELEGRAM_BOT_TOKEN_MARGOT_BOT", ""),
        chat_id=env.get("MARGOT_DM_CHAT_ID", ""),
        run_sync_subprocess=run_sync,
        notify_fn=notify_margot,
    )


def main():
    parser = argparse.ArgumentParser(description="Plaud → Brain ingester")
    parser.add_argument("--backfill", metavar="ISO_DATETIME",
                        help="One-shot. Ignore state; ingest everything since this ISO timestamp.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log what would be done; no writes, no DMs.")
    args = parser.parse_args()

    _configure_logging()
    env = _load_env()
    cfg = _build_default_config(env, backfill_since=args.backfill)

    if args.dry_run:
        cfg.run_sync_subprocess = lambda: log.info("[dry-run] would run sync_wiki_to_supabase.py")
        cfg.notify_fn = lambda **k: log.info("[dry-run] would DM: %s", k.get("text", ""))

    async def go():
        async with connect_real_plaud() as client:
            return await run_once(client, cfg)

    result = asyncio.run(go())
    log.info("plaud-ingest run: %s", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual smoke — `--dry-run`**

Run:
```bash
python3 ~/Pi-CEO/Pi-Dev-Ops/scripts/plaud_ingest.py --dry-run
```
Expected: JSON result printed; no files written to `~/2nd Brain/...`. If you see an authentication prompt or auth_expired status, run the login flow.

Note: If `connect_real_plaud` errors because npx is fetching the MCP package fresh, retry once — subsequent runs use the cache.

- [ ] **Step 3: Tests still pass (CLI not under test)**

```bash
pytest tests/test_plaud_ingest.py -v
```
Expected: 38 passed.

- [ ] **Step 4: Commit**

```bash
git add scripts/plaud_ingest.py
git commit -m "feat(plaud-ingest): CLI entry point with --backfill and --dry-run (Task 12)"
```

---

## Task 13: Patch sync_wiki_to_supabase.py to recurse + preserve subdir in page_id

**Files:**
- Modify: `scripts/sync_wiki_to_supabase.py`
- Create: `tests/test_plaud_sync_patch.py`

- [ ] **Step 1: Write a failing test**

Create `tests/test_plaud_sync_patch.py`:
```python
"""Verify sync_wiki_to_supabase.py recurses into subdirs and uses relative path as id."""
import sys
import importlib.util
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parent.parent / "scripts" / "sync_wiki_to_supabase.py"


def _load():
    spec = importlib.util.spec_from_file_location("syncmod", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sync_uses_rglob_not_glob(tmp_path, monkeypatch):
    mod = _load()
    # Build a wiki dir with one top-level and one nested file
    wiki = tmp_path / "Wiki"
    (wiki / "plaud").mkdir(parents=True)
    (wiki / "top.md").write_text("# Top\n\nbody\n")
    (wiki / "plaud" / "nested.md").write_text("# Nested\n\nbody\n")

    monkeypatch.setattr(mod, "WIKI_DIR", wiki)
    monkeypatch.setattr(mod, "get_service_key", lambda: "fake-key")

    seen_ids: list[str] = []
    def fake_upsert(key, page_id, title, content, tags):
        seen_ids.append(page_id)
        return 201

    monkeypatch.setattr(mod, "upsert_page", fake_upsert)
    mod.main()

    assert "top" in seen_ids
    assert "plaud/nested" in seen_ids
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_plaud_sync_patch.py -v
```
Expected: AssertionError — `"plaud/nested" not in seen_ids` (current script only finds top-level).

- [ ] **Step 3: Apply the 2-line patch**

In `~/Pi-CEO/Pi-Dev-Ops/scripts/sync_wiki_to_supabase.py`, locate:
```python
pages = list(WIKI_DIR.glob("*.md"))
```
Replace with:
```python
pages = list(WIKI_DIR.rglob("*.md"))
```

And locate:
```python
        page_id = p.stem
```
Replace with:
```python
        page_id = str(p.relative_to(WIKI_DIR).with_suffix(""))
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_sync_patch.py -v
```
Expected: 1 passed.

Also re-run the full sync against the live wiki (it's idempotent — upserts won't damage anything):
```bash
SUPABASE_SERVICE_ROLE_KEY=$(grep SUPABASE_UNITE_GROUP_SERVICE_KEY ~/.hermes/.env | cut -d= -f2-) \
  python3 ~/Pi-CEO/Pi-Dev-Ops/scripts/sync_wiki_to_supabase.py | tail -5
```
Expected: prints sync count without errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_wiki_to_supabase.py tests/test_plaud_sync_patch.py
git commit -m "feat(sync): rglob + relative-path page_id so plaud/ subdir syncs (Task 13)"
```

---

## Task 14: `delete-plaud-recording.sh` escape hatch

**Files:**
- Create: `scripts/delete-plaud-recording.sh`
- Create: `tests/test_delete_plaud_recording.sh`

- [ ] **Step 1: Write the script**

Create `~/Pi-CEO/Pi-Dev-Ops/scripts/delete-plaud-recording.sh`:
```bash
#!/usr/bin/env bash
# Delete a Plaud recording from the wiki AND Supabase corpus.
# Usage: delete-plaud-recording.sh <slug>
#   <slug> is the wiki page slug, e.g. 2026-05-17-acme-q2-pricing
#
# Reads SUPABASE_UNITE_GROUP_URL + SUPABASE_UNITE_GROUP_SERVICE_KEY from ~/.hermes/.env.
# Does NOT touch the Plaud cloud unless --purge-plaud is passed.

set -euo pipefail

SLUG="${1:-}"
PURGE_PLAUD="${2:-}"
if [[ -z "$SLUG" ]]; then
  echo "Usage: $(basename "$0") <slug> [--purge-plaud]" >&2
  exit 2
fi

WIKI_DIR="$HOME/2nd Brain/2nd Brain/Wiki"
PLAUD_DIR="$WIKI_DIR/plaud"

# Find the wiki page(s) — handle multi-part files via shared plaud_id
TARGETS=()
for f in "$PLAUD_DIR/$SLUG.md" "$PLAUD_DIR/$SLUG"-part*.md; do
  [[ -f "$f" ]] && TARGETS+=("$f")
done

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "no wiki file matching '$SLUG' under $PLAUD_DIR" >&2
  exit 1
fi

# Load env
ENV_FILE="$HOME/.hermes/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi
SUPA_URL="$(grep '^SUPABASE_UNITE_GROUP_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '\"' | tr -d "'")"
SUPA_KEY="$(grep '^SUPABASE_UNITE_GROUP_SERVICE_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '\"' | tr -d "'")"

for f in "${TARGETS[@]}"; do
  filename="$(basename "$f" .md)"
  page_id="plaud/$filename"
  # Delete from Supabase
  curl -sS -X DELETE \
    -H "apikey: $SUPA_KEY" \
    -H "Authorization: Bearer $SUPA_KEY" \
    "$SUPA_URL/rest/v1/wiki_pages?id=eq.${page_id//\//%2F}" \
    >/dev/null
  # Delete wiki file
  rm "$f"
  # Append log
  echo "$(date -u +%Y-%m-%dT%H:%MZ) | plaud-delete | plaud/$filename.md | manual delete" \
    >> "$WIKI_DIR/log.md"
  echo "deleted: $f"
done

if [[ "$PURGE_PLAUD" == "--purge-plaud" ]]; then
  echo "NOTE: --purge-plaud not yet wired; Plaud cloud copy retained" >&2
fi
```

Make it executable:
```bash
chmod +x ~/Pi-CEO/Pi-Dev-Ops/scripts/delete-plaud-recording.sh
```

- [ ] **Step 2: Write a shell-test driver**

Create `~/Pi-CEO/Pi-Dev-Ops/tests/test_delete_plaud_recording.sh`:
```bash
#!/usr/bin/env bash
# Smoke test for delete-plaud-recording.sh (file-system part only — Supabase is stubbed).
set -e

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Build a fake wiki + env
mkdir -p "$TMP/2nd Brain/2nd Brain/Wiki/plaud"
echo "# Foo" > "$TMP/2nd Brain/2nd Brain/Wiki/plaud/2026-05-17-foo.md"
echo "# Foo part 2" > "$TMP/2nd Brain/2nd Brain/Wiki/plaud/2026-05-17-foo-part2.md"
echo "# Log" > "$TMP/2nd Brain/2nd Brain/Wiki/log.md"
mkdir -p "$TMP/.hermes"
cat > "$TMP/.hermes/.env" <<EOF
SUPABASE_UNITE_GROUP_URL=http://127.0.0.1:9
SUPABASE_UNITE_GROUP_SERVICE_KEY=fake
EOF

HOME="$TMP" \
  ~/Pi-CEO/Pi-Dev-Ops/scripts/delete-plaud-recording.sh 2026-05-17-foo

# Assert both files are gone
test ! -f "$TMP/2nd Brain/2nd Brain/Wiki/plaud/2026-05-17-foo.md"
test ! -f "$TMP/2nd Brain/2nd Brain/Wiki/plaud/2026-05-17-foo-part2.md"
# Assert log line added (2 entries — one per file)
grep -q "plaud-delete" "$TMP/2nd Brain/2nd Brain/Wiki/log.md"

echo "PASS: delete-plaud-recording.sh"
```

Make executable, run:
```bash
chmod +x ~/Pi-CEO/Pi-Dev-Ops/tests/test_delete_plaud_recording.sh
~/Pi-CEO/Pi-Dev-Ops/tests/test_delete_plaud_recording.sh
```
Expected: `PASS: delete-plaud-recording.sh`. Curl call to fake URL will print a connection error to stderr — that's fine, the file deletion still happens.

- [ ] **Step 3: Commit**

```bash
git add scripts/delete-plaud-recording.sh tests/test_delete_plaud_recording.sh
git commit -m "feat(plaud): delete-plaud-recording.sh escape hatch (Task 14)"
```

---

## Task 15: macOS LaunchAgent plist + install

**Files:**
- Create: `scripts/com.phillmcgurk.plaud-ingest.plist.example`
- Create: `~/Library/LaunchAgents/com.phillmcgurk.plaud-ingest.plist` (NOT committed — user-local)

- [ ] **Step 1: Write the plist template**

Create `~/Pi-CEO/Pi-Dev-Ops/scripts/com.phillmcgurk.plaud-ingest.plist.example`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.phillmcgurk.plaud-ingest</string>

  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/env</string>
    <string>python3</string>
    <string>/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/scripts/plaud_ingest.py</string>
  </array>

  <key>StartInterval</key>
  <integer>300</integer>

  <key>RunAtLoad</key>
  <false/>

  <key>StandardOutPath</key>
  <string>/Users/phill-mac/.hermes/logs/plaud-ingest.out</string>

  <key>StandardErrorPath</key>
  <string>/Users/phill-mac/.hermes/logs/plaud-ingest.err</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>/Users/phill-mac</string>
  </dict>
</dict>
</plist>
```

- [ ] **Step 2: Install the LaunchAgent**

```bash
cp ~/Pi-CEO/Pi-Dev-Ops/scripts/com.phillmcgurk.plaud-ingest.plist.example \
   ~/Library/LaunchAgents/com.phillmcgurk.plaud-ingest.plist
mkdir -p ~/.hermes/logs
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.phillmcgurk.plaud-ingest.plist
launchctl print gui/$UID/com.phillmcgurk.plaud-ingest | head -20
```
Expected: `launchctl print` shows the job loaded; `state = running` (briefly) or `state = waiting`.

If `bootstrap` errors with "service already loaded", first run `launchctl bootout gui/$UID/com.phillmcgurk.plaud-ingest` then retry.

- [ ] **Step 3: Wait one cycle, inspect log**

Wait 5–10 min, then:
```bash
tail -20 ~/.hermes/logs/plaud-ingest.log
tail -5 ~/.hermes/logs/plaud-ingest.out
tail -5 ~/.hermes/logs/plaud-ingest.err
```
Expected: at least one `plaud-ingest run: {"ingested": ..., "status": "ok", ...}` line.

If `status` is `auth_expired`, run `npx -y @plaud-ai/mcp@latest login` and complete the browser flow.

- [ ] **Step 4: Commit the template (not the user-local plist)**

```bash
git add scripts/com.phillmcgurk.plaud-ingest.plist.example
git commit -m "feat(plaud-ingest): LaunchAgent template for 5-min cron (Task 15)"
```

---

## Task 16: Wiki integration — index.md + plaud/ seed + smoke test

**Files:**
- Create: `~/2nd Brain/2nd Brain/Wiki/plaud/.gitkeep`
- Modify: `~/2nd Brain/2nd Brain/Wiki/index.md`

- [ ] **Step 1: Seed the plaud/ directory**

```bash
mkdir -p ~/2nd\ Brain/2nd\ Brain/Wiki/plaud
touch ~/2nd\ Brain/2nd\ Brain/Wiki/plaud/.gitkeep
```

- [ ] **Step 2: Add a pointer in `index.md`**

Open `~/2nd Brain/2nd Brain/Wiki/index.md`. At the bottom (or under an existing section header that fits — e.g., a "Live ingestion" or "Auto-generated" section), add:
```markdown

## Live Ingestion

- [Plaud recordings](plaud/_index.md) — auto-ingested every 5 min from the NotePin S.
```

- [ ] **Step 3: Live smoke test — record a 30-sec note**

Pick up the Plaud NotePin S and record a 30-second note titled "test ingest — please ignore". Wait until the phone has uploaded (open the Plaud app, confirm the recording appears).

Then wait up to 10 minutes and verify:
```bash
ls -la ~/2nd\ Brain/2nd\ Brain/Wiki/plaud/ | tail -5
```
Expected: a new `.md` file with today's date and slug "test-ingest-please-ignore" (or similar).

```bash
cat ~/2nd\ Brain/2nd\ Brain/Wiki/log.md | tail -3
```
Expected: an entry `plaud-ingest | plaud/2026-05-17-...md | new recording (...)`.

```bash
tail -1 ~/.hermes/plaud-state.json
```
Expected: `last_seen_id` is the new recording's ID; `last_run_status: "ok"`.

If the Telegram bot is configured, you should also receive a DM in Margot's chat: "📼 New Plaud: test ingest — please ignore (30s). I've added it to the brain."

- [ ] **Step 4: Verify Margot sees it**

In Telegram, message Margot: "what's in my Plaud notes today?"

Expected: Margot references the test recording from her Supabase corpus. If she doesn't see it within 2 minutes, run the sync manually:
```bash
SUPABASE_SERVICE_ROLE_KEY=$(grep SUPABASE_UNITE_GROUP_SERVICE_KEY ~/.hermes/.env | cut -d= -f2-) \
  python3 ~/Pi-CEO/Pi-Dev-Ops/scripts/sync_wiki_to_supabase.py
```

- [ ] **Step 5: Test the delete escape hatch**

```bash
~/Pi-CEO/Pi-Dev-Ops/scripts/delete-plaud-recording.sh 2026-05-17-test-ingest-please-ignore
```
Expected: file gone from `~/2nd Brain/2nd Brain/Wiki/plaud/`; log entry "plaud-delete" added; Supabase row gone (next Margot query won't reference it).

- [ ] **Step 6: Commit any wiki changes** (only if the wiki is itself a git repo — check `cd ~/2nd\ Brain/2nd\ Brain && git status` first; if not a repo, skip)

If the 2nd Brain wiki is git-tracked:
```bash
cd ~/2nd\ Brain/2nd\ Brain
git add Wiki/index.md Wiki/plaud/.gitkeep
git commit -m "feat(wiki): add Plaud live-ingestion section"
```

- [ ] **Step 7: Final Pi-Dev-Ops commit — completion marker**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
# No file changes here, just a tag commit if you want one. Otherwise skip.
```

---

## Task 17: Live integration test (opt-in)

**Files:**
- Create: `tests/test_plaud_ingest_live.py`

- [ ] **Step 1: Write the live test**

Create `~/Pi-CEO/Pi-Dev-Ops/tests/test_plaud_ingest_live.py`:
```python
"""Live integration test — calls the real Plaud MCP. Opt-in via RUN_PLAUD_LIVE=1.

Catches Plaud API schema drift before production cron does.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_ingest


@pytest.mark.skipif(os.environ.get("RUN_PLAUD_LIVE") != "1",
                    reason="set RUN_PLAUD_LIVE=1 to run live Plaud integration test")
def test_live_ingest_one_recording(tmp_path):
    state_path = tmp_path / "state.json"
    wiki_dir = tmp_path / "Wiki"
    plaud_dir = wiki_dir / "plaud"

    cfg = plaud_ingest.IngestConfig(
        state_path=state_path,
        lock_path=tmp_path / "lock",
        wiki_dir=wiki_dir,
        plaud_dir=plaud_dir,
        bot_token="", chat_id="",  # no Telegram DM during test
        run_sync_subprocess=lambda: None,
        notify_fn=lambda **k: None,
    )

    async def go():
        async with plaud_ingest.connect_real_plaud() as client:
            # Force a fresh listing of the user's recordings
            files = await client.list_files_since("2020-01-01")
            assert files, "Plaud account has zero recordings — cannot run live test"
            # Pin state to just-before the OLDEST recording so we ingest at least one
            oldest = min(files, key=lambda f: f["created_at"])
            state = plaud_ingest.load_state(state_path)
            state["last_seen_ts"] = "2020-01-01T00:00:00+00:00"
            plaud_ingest.save_state(state_path, state)
            # Run once
            return await plaud_ingest.run_once(client, cfg)

    result = asyncio.run(go())
    assert result["status"] in ("ok", "locked")
    if result["status"] == "ok":
        assert result["ingested"] >= 1
        written = list(plaud_dir.glob("*.md"))
        assert written, "no wiki file was written"
        # Frontmatter parses
        fm = plaud_ingest._parse_frontmatter(written[0].read_text())
        assert fm and fm.get("type") == "plaud-recording"
```

- [ ] **Step 2: Run the live test once**

```bash
RUN_PLAUD_LIVE=1 pytest tests/test_plaud_ingest_live.py -v -s
```
Expected: 1 passed (or skipped if `RUN_PLAUD_LIVE` is unset).

If the test fails on `list_files` payload shape, the assumptions in `PlaudClient._payload` may be wrong — inspect the actual response and adjust `list_files_since`/`get_note`/`get_transcript` payload paths to match the real schema.

- [ ] **Step 3: Commit**

```bash
git add tests/test_plaud_ingest_live.py
git commit -m "test(plaud-ingest): live integration test gated by RUN_PLAUD_LIVE=1 (Task 17)"
```

---

## Post-implementation: acceptance checklist

Run through the spec's acceptance criteria one final time:

- [ ] A new Plaud recording lands in `wiki/plaud/` within 10 minutes of NotePin syncing
- [ ] Wiki page contains frontmatter + AI summary + full timestamped transcript
- [ ] Recordings >50k chars split into `…-part2.md`, `…-part3.md` cleanly
- [ ] Supabase `wiki_pages` table contains the new row within 1 minute of wiki write
- [ ] Margot, asked "what's in my Plaud notes from today?", references the recording from her corpus
- [ ] Margot, asked for a verbatim quote, can call Plaud MCP `get_transcript` and produce it
- [ ] `delete-plaud-recording.sh <slug>` removes wiki page **and** Supabase row
- [ ] Auth-expired path: ingester DMs Margot once, does not loop
- [ ] Two ingester runs within 5 sec → second exits cleanly via PID lock
- [ ] `wiki/log.md` has an entry for every ingested + every deleted recording

Once all checked: sub-project 1 is complete. Sub-project 2 (meeting follow-through) and sub-project 3 (live in-meeting display) can now be designed against the running ingestion substrate.
