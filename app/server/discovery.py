"""app/server/discovery.py — RA-2026 (HERMES Discovery loop).

Continuous Discovery → Gap Analysis → Proposal pipeline that runs per
persona on a cron cadence. Sibling of the existing autonomy loop
(`app/server/autonomy.py`, RA-1289). The autonomy loop pulls Linear
tickets and executes them; this loop pushes findings into Linear as
new tickets.

Four protocols:

  1. SCAN     — local Gemma 4 26B (ollama) summarises Perplexity
                output for the persona's watch-list. Zero cost.
  2. GAP      — OpenRouter Llama 3.3 70B classifies findings against
                the persona's business charter + current OKRs. Output:
                {finding_id, gap_class, severity 1-10}.
  3. PROPOSAL — Llama 3.3 70B drafts a Linear ticket for sev>=4
                findings; calls swarm.margot_tools.propose_idea with
                originator="discovery_loop" so both `margot-idea` AND
                `discovery-loop` labels are applied.
  4. ESCALATE — sev>=7 findings: Sonnet 4.6 routes to Board /
                Telegram / both. Reuses existing pathways
                (skills/ceo-board, swarm/bots/chief_of_staff).

Public API:

    run_persona_cycle(persona_id) -> CycleReport     # one-shot scan for one persona
    run_discovery_loop()                              # async cron-aware loop

Idempotence: Discovery dedupes findings via sha256(title+url+date)
checkpoints in `~/.hermes/discovery-state.json`. A second cron tick
within the dedup window emits zero new tickets.

Kill-switch: respects TAO_SWARM_ENABLED env (same gate as senior bots)
+ HARD_STOP file (`app/server/kill_switch.py`).

Cost: SCAN $0 (Gemma 4 local); GAP+PROPOSAL ~$0.001/persona/day
(Llama 3.3 70B AkashML); ESCALATE bounded by sev>=7 rate (rare).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("pi-ceo.discovery")

# ── Constants / paths ────────────────────────────────────────────────────────

# State files live under ~/.hermes/ to keep operator visibility consistent
# with Margot/Hermes daemon paths. Override via env for test isolation.
_HERMES_ROOT = Path(os.environ.get(
    "HERMES_ROOT", str(Path.home() / ".hermes")
))
DISCOVERY_STATE_PATH = _HERMES_ROOT / "discovery-state.json"
DISCOVERY_REPORT_DIR = _HERMES_ROOT / "discovery"
CHARTERS_DIR = _HERMES_ROOT / "business-charters"

# Hash-dedup window in days — any finding whose hash was seen inside this
# window is treated as already-known and skipped. 30d is the operator's
# typical re-evaluation cadence.
DEDUP_WINDOW_DAYS: int = 30

# Severity thresholds for protocol routing
SEV_PROPOSAL_MIN: int = 4   # below: archive, no Linear ticket
SEV_ESCALATE_MIN: int = 7   # above: ESCALATE protocol fires alongside PROPOSAL

# Models per protocol (RA-1099 + operator directive: OpenRouter open-source
# first; Anthropic only for hardest tasks)
SCAN_MODEL: str = os.environ.get("DISCOVERY_SCAN_MODEL", "gemma4:26b")
GAP_MODEL: str = os.environ.get(
    "DISCOVERY_GAP_MODEL", "meta-llama/llama-3.3-70b-instruct"
)
PROPOSAL_MODEL: str = os.environ.get(
    "DISCOVERY_PROPOSAL_MODEL", "meta-llama/llama-3.3-70b-instruct"
)


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class Finding:
    """One novel signal surfaced by SCAN."""
    persona_id: str
    title: str
    url: str = ""
    published_date: str = ""
    summary: str = ""
    source: str = "perplexity"   # perplexity | corpus | manual
    raw_query: str = ""

    @property
    def hash(self) -> str:
        """sha256 over (title|url|date) — stable dedup key."""
        key = f"{self.title}|{self.url}|{self.published_date}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


@dataclass
class GapClassification:
    """Output of GAP protocol — one classification per Finding."""
    finding_hash: str
    gap_class: str  # strategic | operational | market | technical | regulatory | competitive
    severity: int   # 1..10
    rationale: str = ""


@dataclass
class CycleReport:
    """Outcome of one persona cycle. Persisted to discovery/<persona>/<ts>.jsonl."""
    persona_id: str
    started_at: str
    finished_at: str = ""
    findings_total: int = 0
    findings_novel: int = 0
    classifications: list[GapClassification] = field(default_factory=list)
    proposals_created: list[str] = field(default_factory=list)  # Linear identifiers
    escalations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    cost_usd: float = 0.0


@dataclass
class PersonaConfig:
    """Resolved configuration for one Discovery persona. Built from the
    business charter file + .harness/projects.json entry."""
    persona_id: str
    linear_project_id: str
    linear_team_id: str
    linear_team_key: str
    charter_path: Path
    charter_text: str = ""
    watchlist: list[str] = field(default_factory=list)  # Perplexity queries
    enabled: bool = True


# ── State management ─────────────────────────────────────────────────────────


def _load_state() -> dict[str, Any]:
    """Load the dedup checkpoint. Schema:
        {
            "version": 1,
            "hashes": {<hash>: {"persona_id": str, "first_seen": iso}}
        }
    """
    if not DISCOVERY_STATE_PATH.exists():
        return {"version": 1, "hashes": {}}
    try:
        return json.loads(DISCOVERY_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("discovery: state load failed (%s) — fresh state", exc)
        return {"version": 1, "hashes": {}}


def _save_state(state: dict[str, Any]) -> None:
    """Atomic write — tmp + replace."""
    DISCOVERY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DISCOVERY_STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(DISCOVERY_STATE_PATH))


def _prune_stale_hashes(state: dict[str, Any]) -> int:
    """Remove hashes older than DEDUP_WINDOW_DAYS. Returns count pruned."""
    cutoff = datetime.now(timezone.utc).timestamp() - (DEDUP_WINDOW_DAYS * 86400)
    hashes = state.get("hashes") or {}
    stale: list[str] = []
    for h, meta in hashes.items():
        try:
            seen_ts = datetime.fromisoformat(meta.get("first_seen", "")).timestamp()
        except (ValueError, TypeError):
            stale.append(h)
            continue
        if seen_ts < cutoff:
            stale.append(h)
    for h in stale:
        del hashes[h]
    return len(stale)


def is_novel(finding: Finding, state: dict[str, Any] | None = None) -> bool:
    """Return True iff this finding's hash is not in the dedup window."""
    s = state if state is not None else _load_state()
    return finding.hash not in (s.get("hashes") or {})


def record_finding(finding: Finding, state: dict[str, Any]) -> None:
    """Mutate state in place to record the finding hash."""
    state.setdefault("hashes", {})[finding.hash] = {
        "persona_id": finding.persona_id,
        "first_seen": datetime.now(timezone.utc).isoformat(),
    }


# ── Persona configuration loader ─────────────────────────────────────────────


def load_persona_config(
    persona_id: str,
    *,
    projects_json_path: Path | None = None,
    charters_dir: Path | None = None,
) -> PersonaConfig | None:
    """Resolve a persona id (e.g. 'restoreassist') against `.harness/projects.json`
    and the business-charter file. Returns None if persona not found or charter
    missing.

    Watch-list is parsed from the charter file's `## Watch-list` section —
    each line beginning with `- ` becomes a Perplexity query.
    """
    pj_path = projects_json_path or (
        Path(__file__).parent.parent.parent / ".harness" / "projects.json"
    )
    cd = charters_dir or CHARTERS_DIR

    try:
        registry = json.loads(pj_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("discovery: projects.json load failed (%s)", exc)
        return None

    project = next(
        (p for p in (registry.get("projects") or []) if p.get("id") == persona_id),
        None,
    )
    if not project:
        log.warning("discovery: persona %r not found in projects.json", persona_id)
        return None

    charter_path = Path(project.get("business_charter") or "")
    if not charter_path.is_absolute():
        charter_path = cd / f"{persona_id}.md"

    charter_text = ""
    watchlist: list[str] = []
    if charter_path.exists():
        try:
            charter_text = charter_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("discovery: charter read failed for %s: %s", persona_id, exc)
        watchlist = _extract_watchlist(charter_text)

    return PersonaConfig(
        persona_id=persona_id,
        linear_project_id=project.get("linear_project_id") or "",
        linear_team_id=project.get("linear_team_id") or "",
        linear_team_key=project.get("linear_team_key") or "",
        charter_path=charter_path,
        charter_text=charter_text,
        watchlist=watchlist,
        enabled=bool(project.get("discovery_enabled", True)),
    )


def _extract_watchlist(charter_text: str) -> list[str]:
    """Parse `## Watch-list` markdown section. Each `- query` line becomes
    a Perplexity query. Empty list on any failure."""
    if not charter_text:
        return []
    lines = charter_text.splitlines()
    out: list[str] = []
    in_section = False
    for raw in lines:
        line = raw.strip()
        if line.lower().startswith("## watch-list") or line.lower().startswith("## watchlist"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            # Next H2 — exit section
            break
        if in_section and line.startswith("- "):
            q = line[2:].strip()
            if q:
                out.append(q)
    return out


# ── Kill-switch / gating ─────────────────────────────────────────────────────


def _is_swarm_enabled() -> bool:
    """Discovery shares the swarm kill-switch convention."""
    return os.environ.get("TAO_SWARM_ENABLED", "0") == "1"


def _is_hard_stop() -> bool:
    """File-flag hard stop. Same path as kill_switch.LoopCounter."""
    flag = Path(os.environ.get(
        "TAO_HARD_STOP_FILE",
        str(Path.home() / ".claude" / "HARD_STOP"),
    ))
    return flag.exists()


# ── SCAN protocol ────────────────────────────────────────────────────────────


def _scan_with_perplexity(query: str) -> list[Finding]:
    """Call mcp.pi_ceo.perplexity_research and shape into Finding records.

    NOTE: actual Perplexity wiring lives in mcp/pi-ceo-server.js; this
    function is the python-side caller-shim. For now it delegates to a
    hook that tests can patch; production wiring lands in a follow-up
    sub-issue when the Discovery loop is enabled in cron.
    """
    fn = _PERPLEXITY_HOOK
    if fn is None:
        log.debug("discovery: no perplexity hook registered — skip scan")
        return []
    try:
        return fn(query) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("discovery: perplexity scan failed for %r: %s", query, exc)
        return []


# Hook the Perplexity caller-shim. Tests patch this directly; production
# wiring (Wave 2 sub-issue) sets it to a real httpx call into the MCP
# server. Keeping it as a module-level hook avoids tangling Discovery
# with the JS MCP transport plumbing in the foundation PR.
_PERPLEXITY_HOOK: Any = None


def set_perplexity_hook(fn) -> None:
    """Register the caller-shim that produces Findings from a Perplexity
    query. Call shape: `fn(query: str) -> list[Finding]`."""
    global _PERPLEXITY_HOOK  # noqa: PLW0603
    _PERPLEXITY_HOOK = fn


def _summarise_with_gemma(prompt: str, *, timeout_s: int = 120) -> str:
    """SCAN-stage summariser. Returns text; "" on any failure (fail-soft)."""
    try:
        from swarm import ollama_client  # noqa: PLC0415
    except ImportError as exc:
        log.warning("discovery: ollama_client unavailable (%s)", exc)
        return ""
    out = ollama_client.chat(
        model=SCAN_MODEL,
        system=(
            "You are a domain analyst summarising research output for a "
            "portfolio business. Produce a concise structured summary "
            "(<=400 words) with one bullet per signal. No preamble, no "
            "tool calls, no markdown fences."
        ),
        user_message=prompt,
        temperature=0.2,
    )
    return (out or "").strip()


def scan(persona: PersonaConfig) -> list[Finding]:
    """Protocol 1 — SCAN. Iterate persona's watch-list, call Perplexity
    per query, accumulate Findings. Each Finding is independently
    summarised by Gemma 4 (fail-soft when Gemma is offline)."""
    findings: list[Finding] = []
    for query in persona.watchlist:
        per_query = _scan_with_perplexity(query)
        for f in per_query:
            f.persona_id = persona.persona_id
            f.raw_query = query
            if not f.summary:
                # Gemma 4 summarises the raw research output for this finding
                blob = (
                    f"Title: {f.title}\nURL: {f.url}\nDate: {f.published_date}\n"
                    f"Source: {f.source}\nQuery: {query}"
                )
                f.summary = _summarise_with_gemma(blob)
            findings.append(f)
    return findings


# ── GAP protocol ─────────────────────────────────────────────────────────────


def _gap_classify(
    finding: Finding,
    persona: PersonaConfig,
    *,
    classifier=None,
) -> GapClassification:
    """Classify one finding against the persona's charter. The classifier
    callable is injected so tests don't need an LLM. Production wiring
    lives in a follow-up sub-issue (Wave 2)."""
    fn = classifier if classifier is not None else _GAP_CLASSIFIER_HOOK
    if fn is None:
        return GapClassification(
            finding_hash=finding.hash, gap_class="operational", severity=4,
            rationale="no_classifier_hook",
        )
    try:
        return fn(finding, persona)
    except Exception as exc:  # noqa: BLE001
        log.warning("discovery: gap classify failed: %s", exc)
        return GapClassification(
            finding_hash=finding.hash, gap_class="operational", severity=4,
            rationale=f"classifier_raised: {exc}",
        )


_GAP_CLASSIFIER_HOOK: Any = None


def set_gap_classifier(fn) -> None:
    """Register the GAP-stage classifier callable.
    Shape: `fn(finding: Finding, persona: PersonaConfig) -> GapClassification`."""
    global _GAP_CLASSIFIER_HOOK  # noqa: PLW0603
    _GAP_CLASSIFIER_HOOK = fn


# ── PROPOSAL protocol ────────────────────────────────────────────────────────


def _propose(
    finding: Finding,
    classification: GapClassification,
    persona: PersonaConfig,
    *,
    drafter=None,
) -> str | None:
    """Draft a Linear ticket and create it via margot_tools.propose_idea.
    Returns the Linear identifier on success, None on any failure
    (logged + recorded on CycleReport).

    The drafter callable composes title + description from the finding +
    classification + persona context. Tests inject a deterministic
    drafter; production wiring lands in a follow-up sub-issue (Wave 2)
    once the Llama 3.3 70B drafting prompt is tuned."""
    fn = drafter if drafter is not None else _PROPOSAL_DRAFTER_HOOK
    title: str
    description: str
    if fn is None:
        # Conservative fallback — title is the finding title, body is a
        # minimal templated rendering. Production drafter is richer.
        title = finding.title[:200] or f"[{persona.persona_id}] novel signal"
        description = (
            f"**Discovery finding** — {persona.persona_id}\n\n"
            f"**Source:** {finding.source}\n\n"
            f"**Query:** {finding.raw_query}\n\n"
            f"**Gap class:** {classification.gap_class} "
            f"(severity {classification.severity}/10)\n\n"
            f"**Summary:**\n{finding.summary}\n\n"
            f"**URL:** {finding.url}\n"
        )
    else:
        try:
            title, description = fn(finding, classification, persona)
        except Exception as exc:  # noqa: BLE001
            log.warning("discovery: drafter raised: %s", exc)
            return None

    try:
        from swarm import margot_tools  # noqa: PLC0415
    except ImportError as exc:
        log.warning("discovery: margot_tools unavailable (%s)", exc)
        return None

    # Map severity to priority. Sev 7-10 => Urgent (1) / High (2) /
    # remainder => Medium (3). Linear priorities: 0=None, 1=Urgent,
    # 2=High, 3=Medium, 4=Low.
    if classification.severity >= 9:
        priority = 1
    elif classification.severity >= 7:
        priority = 2
    elif classification.severity >= 4:
        priority = 3
    else:
        priority = 4

    out = margot_tools.propose_idea(
        title=title,
        description=description,
        team=persona.linear_team_key or "RA",
        priority=priority,
        originator="discovery_loop",
    )
    if out.get("status") == "created":
        return out.get("identifier")
    log.warning(
        "discovery: propose_idea did not create ticket (status=%s, error=%s)",
        out.get("status"), out.get("error"),
    )
    return None


_PROPOSAL_DRAFTER_HOOK: Any = None


def set_proposal_drafter(fn) -> None:
    """Register the PROPOSAL-stage drafter.
    Shape: `fn(finding, classification, persona) -> (title, description)`."""
    global _PROPOSAL_DRAFTER_HOOK  # noqa: PLW0603
    _PROPOSAL_DRAFTER_HOOK = fn


# ── ESCALATE protocol ────────────────────────────────────────────────────────


def _escalate(
    finding: Finding,
    classification: GapClassification,
    persona: PersonaConfig,
    proposal_id: str | None,
    *,
    router=None,
) -> dict[str, Any]:
    """Sev>=7 router. Returns a dict describing what fired. Production
    wiring (Sonnet 4.6 routing decision -> Board / Telegram) lands in a
    follow-up sub-issue once Discovery has produced enough sev>=7 signal
    to tune the routing rubric."""
    fn = router if router is not None else _ESCALATION_ROUTER_HOOK
    if fn is None:
        return {
            "fired": False,
            "reason": "no_router_hook",
            "proposal_id": proposal_id,
        }
    try:
        return fn(finding, classification, persona, proposal_id) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("discovery: escalation router raised: %s", exc)
        return {"fired": False, "reason": f"router_raised: {exc}"}


_ESCALATION_ROUTER_HOOK: Any = None


def set_escalation_router(fn) -> None:
    """Register the ESCALATE router.
    Shape: `fn(finding, classification, persona, proposal_id) -> dict`."""
    global _ESCALATION_ROUTER_HOOK  # noqa: PLW0603
    _ESCALATION_ROUTER_HOOK = fn


# ── Per-persona cycle ────────────────────────────────────────────────────────


def run_persona_cycle(persona_id: str) -> CycleReport:
    """One full Discovery cycle for one persona. Returns CycleReport.

    This is the cron-callable entry point. The cron type "discovery" in
    `app/server/cron_triggers.py` invokes this with the trigger's
    `persona` field.
    """
    started = datetime.now(timezone.utc).isoformat()
    report = CycleReport(persona_id=persona_id, started_at=started)

    if not _is_swarm_enabled():
        report.error = "swarm_disabled"
        report.finished_at = datetime.now(timezone.utc).isoformat()
        return report
    if _is_hard_stop():
        report.error = "hard_stop"
        report.finished_at = datetime.now(timezone.utc).isoformat()
        return report

    persona = load_persona_config(persona_id)
    if persona is None or not persona.enabled:
        report.error = (
            "persona_disabled" if persona and not persona.enabled
            else "persona_not_found"
        )
        report.finished_at = datetime.now(timezone.utc).isoformat()
        return report

    # SCAN
    findings = scan(persona)
    report.findings_total = len(findings)

    # Dedup
    state = _load_state()
    _prune_stale_hashes(state)
    novel: list[Finding] = []
    for f in findings:
        if is_novel(f, state):
            novel.append(f)
            record_finding(f, state)
    report.findings_novel = len(novel)
    _save_state(state)

    # GAP + PROPOSAL + ESCALATE
    for f in novel:
        cls = _gap_classify(f, persona)
        report.classifications.append(cls)
        if cls.severity < SEV_PROPOSAL_MIN:
            continue
        proposal_id = _propose(f, cls, persona)
        if proposal_id:
            report.proposals_created.append(proposal_id)
        if cls.severity >= SEV_ESCALATE_MIN:
            esc = _escalate(f, cls, persona, proposal_id)
            report.escalations.append(esc)

    report.finished_at = datetime.now(timezone.utc).isoformat()
    _persist_report(report)
    return report


def _persist_report(report: CycleReport) -> None:
    """Write CycleReport JSONL line to discovery/<persona>/<ts>.jsonl."""
    try:
        outdir = DISCOVERY_REPORT_DIR / report.persona_id
        outdir.mkdir(parents=True, exist_ok=True)
        ts = report.started_at.replace(":", "").replace("-", "")[:15]
        path = outdir / f"{ts}.jsonl"
        path.write_text(
            json.dumps(asdict(report), default=str) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("discovery: report persist failed: %s", exc)


# ── Cron-callable shim ───────────────────────────────────────────────────────


async def _fire_discovery_trigger(trigger: dict, log_arg) -> None:
    """Cron dispatcher hook. trigger = {type: 'discovery', persona: <id>, ...}.

    Wired in `app/server/cron_triggers.py`'s `_fire_trigger` dispatch
    table. Async-shim around the sync `run_persona_cycle` so the cron
    loop's `asyncio.gather` pattern stays consistent.
    """
    import asyncio as _aio  # noqa: PLC0415

    persona_id = trigger.get("persona") or trigger.get("id", "").split("-")[-1]
    if not persona_id:
        log_arg.warning("discovery: trigger %s missing persona field", trigger.get("id"))
        return
    log_arg.info("Firing discovery cycle persona=%s", persona_id)
    started = time.monotonic()
    report = await _aio.to_thread(run_persona_cycle, persona_id)
    elapsed = round(time.monotonic() - started, 2)
    log_arg.info(
        "Discovery cycle persona=%s done in %.2fs: total=%d novel=%d proposals=%d escalations=%d error=%s",
        persona_id, elapsed,
        report.findings_total, report.findings_novel,
        len(report.proposals_created), len(report.escalations),
        report.error,
    )


__all__ = [
    "DEDUP_WINDOW_DAYS",
    "DISCOVERY_REPORT_DIR",
    "DISCOVERY_STATE_PATH",
    "Finding",
    "GapClassification",
    "CycleReport",
    "PersonaConfig",
    "SEV_ESCALATE_MIN",
    "SEV_PROPOSAL_MIN",
    "is_novel",
    "load_persona_config",
    "record_finding",
    "run_persona_cycle",
    "scan",
    "set_escalation_router",
    "set_gap_classifier",
    "set_perplexity_hook",
    "set_proposal_drafter",
]
