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


import contextlib
import errno


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as e:
        return e.errno == errno.EPERM
    return True


@contextlib.contextmanager
def pid_lock(lockfile: Path):
    """Acquire a PID-based lock. Yields True if acquired, False if held by live PID.
    Stale (dead-PID) lock files are auto-cleared and the lock is taken."""
    acquired = False
    if lockfile.exists():
        try:
            holder = int(lockfile.read_text().strip())
            if _pid_alive(holder):
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
        text = md.read_text()
        fm = _parse_frontmatter(text)
        if not fm or fm.get("type") != "plaud-recording":
            continue
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
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
    except Exception as e:
        log.warning("notify_margot: %s", e)


import asyncio
from contextlib import asynccontextmanager


class PlaudClient:
    """Thin async wrapper. Takes an initialized `mcp.ClientSession` (or duck-typed
    fake in tests). The factory `connect_real_plaud()` spawns the npm MCP server."""

    def __init__(self, session):
        self.session = session

    @staticmethod
    def _payload(result) -> dict:
        """Extract JSON payload from an MCP tool result."""
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
    prev_status = state.get("last_run_status")
    state["consecutive_failures"] = prev_failures + 1
    state["last_error"] = msg

    if is_auth:
        state["last_run_status"] = "auth_expired"
        if prev_status != "auth_expired":
            cfg.notify_fn(bot_token=cfg.bot_token, chat_id=cfg.chat_id,
                          text="⚠️ Plaud token expired — open Hermes and run `plaud login`.")
        save_state(cfg.state_path, state)
        return {"ingested": 0, "status": "auth_expired", "error": msg}

    state["last_run_status"] = "network_error"
    if state["consecutive_failures"] == 6:
        cfg.notify_fn(bot_token=cfg.bot_token, chat_id=cfg.chat_id,
                      text="⚠️ Plaud unreachable for 30 min.")
    save_state(cfg.state_path, state)
    return {"ingested": 0, "status": "network_error", "error": msg}
