"""swarm/analyst.py — Research & intelligence direction layer.

Implements the Analyst doctrine (skills/analyst/SKILL.md): frames questions,
grades evidence, produces §11 deliverables, and runs daily senior-agent breach
reviews. Margot calls maybe_analyse_research after research turns; the
orchestrator calls run_breach_review daily.

Public API:
    maybe_analyse_research(topic, finding, findings, *, turn_id=None)
        -> AnalystDeliverable
    should_run_breach_review(state) -> bool
    run_breach_review(*, repo_root=None) -> dict[str, Any]
"""
from __future__ import annotations

import json
import ipaddress
import logging
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.analyst")

STATE_KEY = "last_analyst_breach_review"
ANALYST_SUBDIR = "analyst"
ANALYST_LEDGER_REL = ".harness/swarm/analyst_state.jsonl"
SENIOR_LEDGERS = (
    (".harness/swarm/cmo_state.jsonl", "cmo"),
    (".harness/swarm/cfo_state.jsonl", "cfo"),
    (".harness/swarm/cto_state.jsonl", "cto"),
    (".harness/swarm/cs_state.jsonl", "cs"),
)


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class EvidenceItem:
    claim: str
    grade: str = "C3"
    tag: str = "[INF]"

    def to_dict(self) -> dict[str, str]:
        return {"claim": self.claim, "grade": self.grade, "tag": self.tag}


@dataclass
class AnalystDeliverable:
    question: str
    answer: str
    confidence: str = "~50%"
    key_evidence: list[EvidenceItem] = field(default_factory=list)
    leading_alternative: str = ""
    critical_unknowns: list[str] = field(default_factory=list)
    kill_switch: str = ""
    next_collection: str = ""
    turn_id: str | None = None
    analyst_path: str = ""

    def is_complete(self) -> bool:
        return bool(
            self.answer.strip()
            and self.leading_alternative.strip()
            and self.critical_unknowns
            and self.kill_switch.strip()
        )

    def to_markdown(self) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines = [
            "---",
            "type: analyst-deliverable",
            f"updated: {today}",
            f"confidence: {self.confidence}",
        ]
        if self.turn_id:
            lines.append(f"turn_id: {self.turn_id}")
        lines.extend(["---", "", "## Question", "", self.question, ""])
        lines.extend([f"## Answer ({self.confidence})", "", self.answer, ""])
        lines.append("## Key evidence")
        lines.append("")
        if self.key_evidence:
            for ev in self.key_evidence:
                lines.append(f"- {ev.tag} `{ev.grade}` — {ev.claim}")
        else:
            lines.append("- _No graded evidence captured._")
        lines.append("")
        lines.extend(["## Leading alternative", "", self.leading_alternative or "_None stated._", ""])
        lines.append("## Critical unknowns")
        lines.append("")
        for unk in self.critical_unknowns or ["_None ranked._"]:
            lines.append(f"- {unk}")
        lines.append("")
        lines.extend(["## Kill-switch", "", self.kill_switch or "_Not stated._", ""])
        lines.extend(["## Recommended next collection", "", self.next_collection or "_None._", ""])
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["key_evidence"] = [e.to_dict() for e in self.key_evidence]
        d["complete"] = self.is_complete()
        return d


# ── Helpers ──────────────────────────────────────────────────────────────────


def _repo_root(repo_root: Path | None = None) -> Path:
    return repo_root or Path(__file__).resolve().parents[1]


def _wiki_dir() -> Path:
    from . import config  # noqa: PLC0415
    return Path(config.BRAIN1_WIKI_DIR)


def _slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:max_len] or "finding").rstrip("-")


def _call_llm(prompt: str) -> str:
    """Gemma 4 (local) → Gemini fallback — same pattern as wiki_query."""
    try:
        from . import config as _cfg, ollama_client  # noqa: PLC0415
        result = ollama_client.chat(
            model=_cfg.OLLAMA_TRIAGE_MODEL_HEAVY,
            system=(
                "You are the Analyst — directing intelligence for growth and "
                "sustainability. Reply with JSON only when asked."
            ),
            user_message=prompt,
            temperature=0.2,
        )
        if result:
            return result
    except Exception as exc:  # noqa: BLE001
        log.debug("analyst: ollama unavailable (%s)", exc)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        key_file = Path.home() / ".margot" / "gemini-api-key.txt"
        if key_file.exists():
            api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        raise RuntimeError("No LLM available for analyst synthesis")

    text_model = (
        os.environ.get("GEMINI_TEXT_MODEL")
        or os.environ.get("MARGOT_TEXT_MODEL")
        or "gemini-3.5-flash"
    )
    text_model = text_model.removeprefix("models/")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(text_model, safe='')}:generateContent"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1800,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Gemini analyst HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Gemini analyst request failed: {exc}") from exc

    parts: list[str] = []
    for candidate in payload.get("candidates", []) or []:
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            text = part.get("text")
            if text:
                parts.append(str(text))
    text = "\n".join(parts).strip()
    if not text:
        raise RuntimeError("Gemini analyst empty response")
    return text


def _parse_llm_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


def _findings_block(findings: list[dict]) -> str:
    if not findings:
        return "_No structured collector payloads._"
    parts: list[str] = []
    for i, f in enumerate(findings[:8], 1):
        topic = f.get("topic", f.get("source", f"finding-{i}"))
        summary = f.get("summary") or f.get("body") or json.dumps(f, ensure_ascii=False)[:600]
        parts.append(f"### Collector {i}: {topic}\n{summary}")
    return "\n\n".join(parts)


def _deterministic_deliverable(
    topic: str,
    finding: str,
    findings: list[dict],
    *,
    turn_id: str | None = None,
) -> AnalystDeliverable:
    """Template deliverable when LLM is unavailable (PC dev / offline)."""
    excerpt = finding.strip()[:400] or "_Empty finding body._"
    evidence: list[EvidenceItem] = []
    for f in findings[:5]:
        summary = str(f.get("summary") or f.get("body") or "")[:200]
        if summary:
            evidence.append(EvidenceItem(
                claim=summary,
                grade="C3",
                tag="[OBS]" if f.get("depth") == "wiki" else "[INF]",
            ))
    if not evidence:
        evidence.append(EvidenceItem(
            claim=excerpt[:200],
            grade="D4",
            tag="[INF]",
        ))
    return AnalystDeliverable(
        question=f"What does the evidence say about: {topic}?",
        answer=excerpt,
        confidence="~50%",
        key_evidence=evidence,
        leading_alternative=(
            "The opposite may hold — insufficient independent corroboration "
            "to reject it without further collection."
        ),
        critical_unknowns=[
            "Primary-source confirmation for load-bearing numeric claims",
            "Recency of market/competitor data if time-sensitive",
        ],
        kill_switch=(
            "Independent primary data contradicting the leading conclusion "
            "would overturn this evaluation."
        ),
        next_collection=(
            "Re-task margot-bridge or marketing-icp-research on the highest-leverage "
            "unknown; check wiki-query first."
        ),
        turn_id=turn_id,
    )


def _synthesise_deliverable(
    topic: str,
    finding: str,
    findings: list[dict],
    *,
    turn_id: str | None = None,
) -> AnalystDeliverable:
    prompt = (
        "Produce an Analyst §11 deliverable as JSON only (no markdown fences).\n\n"
        f"Topic / user question: {topic}\n\n"
        f"Margot synthesis:\n{finding[:6000]}\n\n"
        f"Collector payloads:\n{_findings_block(findings)}\n\n"
        "Schema:\n"
        "{\n"
        '  "question": "precise question + decision it serves",\n'
        '  "answer": "conclusion",\n'
        '  "confidence": "~95%"| "~75%"| "~50%"| "~25%"| "~5%",\n'
        '  "key_evidence": [{"claim":"...", "grade":"B2", "tag":"[OBS]|[INF]|[SPEC]"}],\n'
        '  "leading_alternative": "best competing hypothesis + why rejected",\n'
        '  "critical_unknowns": ["ranked gaps"],\n'
        '  "kill_switch": "evidence that would overturn conclusion",\n'
        '  "next_collection": "single highest-leverage next fetch"\n'
        "}\n"
        "Rules: tag every claim layer; grade source+content (NATO/Admiralty); "
        "never omit leading_alternative, critical_unknowns, or kill_switch."
    )
    try:
        data = _parse_llm_json(_call_llm(prompt))
    except Exception as exc:  # noqa: BLE001
        log.warning("analyst: LLM synthesis failed (%s) — deterministic fallback", exc)
        return _deterministic_deliverable(topic, finding, findings, turn_id=turn_id)

    evidence = [
        EvidenceItem(
            claim=str(e.get("claim", "")),
            grade=str(e.get("grade", "C3")),
            tag=str(e.get("tag", "[INF]")),
        )
        for e in (data.get("key_evidence") or [])
        if e.get("claim")
    ]
    return AnalystDeliverable(
        question=str(data.get("question") or f"What does the evidence say about: {topic}?"),
        answer=str(data.get("answer") or finding[:500]),
        confidence=str(data.get("confidence") or "~50%"),
        key_evidence=evidence or _deterministic_deliverable(topic, finding, findings).key_evidence,
        leading_alternative=str(data.get("leading_alternative") or ""),
        critical_unknowns=[str(u) for u in (data.get("critical_unknowns") or []) if u],
        kill_switch=str(data.get("kill_switch") or ""),
        next_collection=str(data.get("next_collection") or ""),
        turn_id=turn_id,
    )


def _obsidian_base_url() -> str:
    from . import config  # noqa: PLC0415
    if config.OBSIDIAN_REMOTE_URL:
        return config.OBSIDIAN_REMOTE_URL.rstrip("/")
    return config.OBSIDIAN_BASE_URL.rstrip("/")


def _should_override_obsidian_dns(host: str, remote_ip: str) -> bool:
    if not host or not remote_ip or host in {"localhost", "127.0.0.1", "::1"}:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def _mirror_obsidian(vault_relative_path: str, content: str) -> bool:
    """Write note to Obsidian vault — REST API or filesystem fallback."""
    from . import config  # noqa: PLC0415

    # Off-Mac runtimes (Railway, Windows collectors) must use the REST bridge.
    # A configured OBSIDIAN_VAULT path inside a container can otherwise become a
    # false-positive local write that never reaches the founder's Mac Mini vault.
    if config.OBSIDIAN_REMOTE_URL:
        return _mirror_obsidian_rest(vault_relative_path, content)

    if config.OBSIDIAN_VAULT:
        try:
            abs_path = Path(config.OBSIDIAN_VAULT) / vault_relative_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")
            log.debug("analyst: obsidian filesystem write %s", vault_relative_path)
            return True
        except OSError as exc:
            log.warning("analyst: obsidian filesystem write failed (%s)", exc)

    return _mirror_obsidian_rest(vault_relative_path, content)


def _mirror_obsidian_rest(vault_relative_path: str, content: str) -> bool:
    """Write note to Obsidian through Local REST API."""
    from . import config  # noqa: PLC0415

    token = config.OBSIDIAN_TOKEN
    if not token:
        return False

    encoded = "/".join(urllib.parse.quote(seg) for seg in vault_relative_path.split("/"))
    url = f"{_obsidian_base_url()}/vault/{encoded}"
    parsed = urllib.parse.urlparse(url)
    body = content.encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/markdown",
            "Content-Length": str(len(body)),
        },
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        remote_ip = getattr(config, "OBSIDIAN_REMOTE_IP", "")
        host = parsed.hostname or ""
        original_getaddrinfo = socket.getaddrinfo
        override_dns = _should_override_obsidian_dns(host, remote_ip)
        if override_dns:
            def _getaddrinfo(name: str, port: int, *args: Any, **kwargs: Any) -> Any:
                if name == host:
                    return original_getaddrinfo(remote_ip, port, *args, **kwargs)
                return original_getaddrinfo(name, port, *args, **kwargs)

            socket.getaddrinfo = _getaddrinfo
        try:
            resp_ctx = urllib.request.urlopen(req, context=ctx, timeout=15)
        finally:
            if override_dns:
                socket.getaddrinfo = original_getaddrinfo
        with resp_ctx as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("analyst: obsidian REST write failed (%s)", exc)
        return False


def _write_analyst_note(
    deliverable: AnalystDeliverable,
    *,
    repo_root: Path | None = None,
) -> str:
    """Persist deliverable under Wiki/analyst/ and optional Obsidian mirror."""
    wdir = _wiki_dir()
    analyst_dir = wdir / ANALYST_SUBDIR
    analyst_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _slugify(deliverable.question)
    filename = f"{today}-{slug}.md"
    rel_path = f"{ANALYST_SUBDIR}/{filename}"
    note_path = wdir / rel_path
    markdown = deliverable.to_markdown()
    note_path.write_text(markdown, encoding="utf-8")
    deliverable.analyst_path = rel_path

    obsidian_rel = f"Wiki/{rel_path}"
    _mirror_obsidian(obsidian_rel, markdown)

    ledger = _repo_root(repo_root) / ANALYST_LEDGER_REL
    ledger.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "path": rel_path,
        "turn_id": deliverable.turn_id,
        "confidence": deliverable.confidence,
        "complete": deliverable.is_complete(),
    }
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return rel_path


def _load_last_jsonl_row(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    last: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    return last


def _collect_breaches(repo_root: Path) -> list[dict[str, Any]]:
    """Read senior-agent ledgers and detect metric breaches."""
    breaches: list[dict[str, Any]] = []
    root = _repo_root(repo_root)

    try:
        from . import cfo as _cfo  # noqa: PLC0415
        p = root / ".harness/swarm/cfo_state.jsonl"
        row = _load_last_jsonl_row(p)
        if row:
            try:
                curr = _cfo.Metrics(**{k: v for k, v in row.items() if k in _cfo.Metrics.__dataclass_fields__})
                prev = _cfo.load_last_snapshot(row.get("business_id", ""), repo_root=root)
                for b in _cfo.detect_breaches(curr, prev):
                    breaches.append({"agent": "cfo", "metric": b.metric, "severity": b.severity, "note": b.note})
            except (TypeError, ValueError) as exc:
                log.debug("analyst: cfo breach parse skip (%s)", exc)
    except Exception as exc:  # noqa: BLE001
        log.debug("analyst: cfo breach scan skip (%s)", exc)

    try:
        from . import cmo as _cmo  # noqa: PLC0415
        p = root / ".harness/swarm/cmo_state.jsonl"
        row = _load_last_jsonl_row(p)
        if row:
            try:
                curr = _cmo.MarketingMetrics(**{
                    k: v for k, v in row.items()
                    if k in _cmo.MarketingMetrics.__dataclass_fields__
                })
                for b in _cmo.detect_breaches(curr, None):
                    breaches.append({"agent": "cmo", "metric": b.metric, "severity": b.severity, "note": b.note})
            except (TypeError, ValueError) as exc:
                log.debug("analyst: cmo breach parse skip (%s)", exc)
    except Exception as exc:  # noqa: BLE001
        log.debug("analyst: cmo breach scan skip (%s)", exc)

    try:
        from . import cto as _cto  # noqa: PLC0415
        p = root / ".harness/swarm/cto_state.jsonl"
        row = _load_last_jsonl_row(p)
        if row:
            try:
                curr = _cto.PlatformMetrics(**{
                    k: v for k, v in row.items()
                    if k in _cto.PlatformMetrics.__dataclass_fields__
                })
                for b in _cto.detect_breaches(curr, None):
                    breaches.append({"agent": "cto", "metric": b.metric, "severity": b.severity, "note": b.note})
            except (TypeError, ValueError) as exc:
                log.debug("analyst: cto breach parse skip (%s)", exc)
    except Exception as exc:  # noqa: BLE001
        log.debug("analyst: cto breach scan skip (%s)", exc)

    try:
        from . import cs as _cs  # noqa: PLC0415
        p = root / ".harness/swarm/cs_state.jsonl"
        row = _load_last_jsonl_row(p)
        if row:
            try:
                curr = _cs.CsMetrics(**{
                    k: v for k, v in row.items()
                    if k in _cs.CsMetrics.__dataclass_fields__
                })
                for b in _cs.detect_breaches(curr, None):
                    breaches.append({"agent": "cs", "metric": b.metric, "severity": b.severity, "note": b.note})
            except (TypeError, ValueError) as exc:
                log.debug("analyst: cs breach parse skip (%s)", exc)
    except Exception as exc:  # noqa: BLE001
        log.debug("analyst: cs breach scan skip (%s)", exc)

    return breaches


# ── Public entry points ───────────────────────────────────────────────────────


def maybe_analyse_research(
    topic: str,
    finding: str,
    findings: list[dict] | None = None,
    *,
    turn_id: str | None = None,
    repo_root: Path | None = None,
) -> AnalystDeliverable:
    """Grade research output and write Wiki/analyst/ deliverable.

    Called by margot_bot after research turns. Respects TAO_ANALYST_ENABLED.
    Falls back to deterministic template when no LLM is reachable (PC dev).
    """
    from . import config  # noqa: PLC0415

    if not config.ANALYST_ENABLED:
        return _deterministic_deliverable(topic, finding, findings or [], turn_id=turn_id)

    payload = findings or []
    deliverable = _synthesise_deliverable(topic, finding, payload, turn_id=turn_id)

    if not deliverable.leading_alternative:
        fb = _deterministic_deliverable(topic, finding, payload, turn_id=turn_id)
        deliverable.leading_alternative = fb.leading_alternative
    if not deliverable.critical_unknowns:
        deliverable.critical_unknowns = _deterministic_deliverable(
            topic, finding, payload,
        ).critical_unknowns
    if not deliverable.kill_switch:
        deliverable.kill_switch = _deterministic_deliverable(
            topic, finding, payload,
        ).kill_switch
    if not deliverable.next_collection:
        deliverable.next_collection = _deterministic_deliverable(
            topic, finding, payload,
        ).next_collection

    try:
        _write_analyst_note(deliverable, repo_root=repo_root)
    except OSError as exc:
        log.warning("analyst: could not write wiki note (%s)", exc)

    return deliverable


def should_run_breach_review(state: dict) -> bool:
    """True if daily senior-agent breach review has not run today."""
    last = state.get(STATE_KEY)
    if not last:
        return True
    try:
        return date.fromisoformat(str(last)[:10]) < date.today()
    except (ValueError, TypeError):
        return True


def run_breach_review(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Scan senior-agent ledgers for breaches; file Analyst note if any."""
    from . import config  # noqa: PLC0415

    if not config.ANALYST_ENABLED:
        return {"status": "disabled", "breaches": []}

    breaches = _collect_breaches(repo_root)
    if not breaches:
        return {"status": "clean", "breaches": []}

    lines = [f"- **{b['agent']}** `{b['metric']}` ({b['severity']}): {b['note']}" for b in breaches]
    finding = "## Senior-agent breaches\n\n" + "\n".join(lines)
    deliverable = _deterministic_deliverable(
        "Daily growth/sustainability breach review",
        finding,
        [{"topic": "breaches", "summary": b["note"]} for b in breaches],
    )
    deliverable.question = (
        "Which growth or sustainability breaches require root-cause collection today?"
    )
    deliverable.answer = (
        f"{len(breaches)} active breach(es) across senior-agent ledgers. "
        "Root-cause collection recommended before spend or scale decisions."
    )
    deliverable.confidence = "~75%"
    deliverable.next_collection = (
        "Task the owning senior agent metric + wiki-query for prior context; "
        "run ACH on the highest-severity breach first."
    )

    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        wdir = _wiki_dir()
        analyst_dir = wdir / ANALYST_SUBDIR
        analyst_dir.mkdir(parents=True, exist_ok=True)
        rel = f"{ANALYST_SUBDIR}/breach-review-{today}.md"
        deliverable.analyst_path = rel
        markdown = deliverable.to_markdown()
        (wdir / rel).write_text(markdown, encoding="utf-8")
        _mirror_obsidian(f"Wiki/{rel}", markdown)
    except OSError as exc:
        log.warning("analyst: breach review write failed (%s)", exc)

    return {"status": "filed", "breaches": breaches, "path": deliverable.analyst_path}


__all__ = [
    "AnalystDeliverable",
    "EvidenceItem",
    "STATE_KEY",
    "maybe_analyse_research",
    "should_run_breach_review",
    "run_breach_review",
]
