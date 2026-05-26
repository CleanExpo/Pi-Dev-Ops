"""Nexus daily scheduler — pure-logic always-on driver.

Phase B.5 / B8. Triggered at 06:00 local by app/server/app_factory.py's
startup hook (gated on NEXUS_SCHEDULER_ENABLED=1). One cycle per
window_key (UTC date by default); re-firing within the same window
is a no-op.

Process:

  1. Compute window_key from clock.now() — default '%Y-%m-%d' (daily).
  2. Read last_run_marker_path; if its content == window_key, skip
     (returns CycleSummary.skipped_idempotent=True).
  3. Append audit: nexus_scheduler.start (policy_level='auto').
  4. Drive loop_runner.run_due_loops().
  5. Per workspace_slug, generate_bra() — wrapped in try/except so one
     workspace's LLM failure does NOT poison the others.
  6. Append audit: nexus_scheduler.success (or .failure on uncaught raise).
  7. Update last_run_marker.
  8. Return CycleSummary.

DRY_RUN: skips run_due_loops + generate_bra. Audit + idempotency marker
still update so a real run can't immediately re-fire on top of a dry run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .audit import build_audit_row
from .bra import BRAReport, generate_bra
from .discovery_loop import ClockProtocol, LLMProtocol, LoopsStore, RunSummary
from .loop_runner import run_due_loops
from .outcomes import OutcomesStore

log = logging.getLogger("pi-ceo.nexus.scheduler")

DEFAULT_WINDOW_KEY_FORMAT = "%Y-%m-%d"
DEFAULT_BRA_WINDOW = "7d"


class AuditStore(Protocol):
    def append(self, row) -> str: ...


@dataclass(frozen=True)
class CycleSummary:
    window_key: str
    started_at: str
    ended_at: str
    dry_run: bool
    skipped_idempotent: bool = False
    loop_summary: RunSummary | None = None
    bra_reports: dict[str, BRAReport] = field(default_factory=dict)
    workspaces_failed: tuple[str, ...] = ()


def _read_marker(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except OSError:
        return ""


def _write_marker(path: Path | None, window_key: str) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(window_key, encoding="utf-8")
    except OSError as exc:
        log.warning("scheduler marker write failed (non-fatal): %s", exc)


def _safe_append(audit_store: AuditStore | None, **kw) -> None:
    if audit_store is None:
        return
    try:
        row = build_audit_row(**kw)
        audit_store.append(row)
    except Exception as exc:  # noqa: BLE001 — audit must never block
        log.warning("scheduler audit append failed (non-fatal): %s", exc)


def run_nexus_cycle(
    *,
    workspace_slugs: list[str],
    loops_store: LoopsStore,
    outcomes_store: OutcomesStore,
    llm: LLMProtocol,
    clock: ClockProtocol,
    audit_store: AuditStore | None = None,
    last_run_marker_path: Path | None = None,
    window_key_format: str = DEFAULT_WINDOW_KEY_FORMAT,
    bra_window: str = DEFAULT_BRA_WINDOW,
    dry_run: bool = False,
) -> CycleSummary:
    """Drive one Nexus daily cycle. Never raises — failures surface in
    the returned CycleSummary fields.
    """
    started = clock.now()
    window_key = started.strftime(window_key_format)
    started_at_iso = started.isoformat()

    # ---- idempotency guard ----------------------------------------
    if _read_marker(last_run_marker_path) == window_key:
        log.info("nexus scheduler skipped (idempotent) window=%s", window_key)
        return CycleSummary(
            window_key=window_key,
            started_at=started_at_iso,
            ended_at=started_at_iso,
            dry_run=dry_run,
            skipped_idempotent=True,
        )

    _safe_append(
        audit_store,
        actor="nexus.scheduler",
        action="nexus_scheduler.start",
        args={"window_key": window_key, "workspaces": len(workspace_slugs),
              "dry_run": dry_run},
        policy_level="auto",
        result="ok",
    )

    # ---- discovery loops + BRA per workspace ----------------------
    loop_summary: RunSummary | None = None
    bra_reports: dict[str, BRAReport] = {}
    workspaces_failed: list[str] = []

    if not dry_run:
        try:
            loop_summary = run_due_loops(
                loops_store=loops_store,
                outcomes_store=outcomes_store,
                llm=llm,
                clock=clock,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("nexus scheduler loop_runner failed (non-fatal): %s", exc)
            loop_summary = None

        for slug in workspace_slugs:
            try:
                bra_reports[slug] = generate_bra(
                    workspace_slug=slug, window=bra_window,  # type: ignore[arg-type]
                    outcomes_store=outcomes_store, llm=llm,
                )
            except Exception as exc:  # noqa: BLE001 — failure isolation
                log.warning(
                    "nexus scheduler BRA failed for workspace=%s: %s", slug, exc,
                )
                workspaces_failed.append(slug)

    ended = clock.now()
    _safe_append(
        audit_store,
        actor="nexus.scheduler",
        action="nexus_scheduler.success" if not workspaces_failed else "nexus_scheduler.partial",
        args={
            "window_key": window_key,
            "loops_ok": loop_summary.ok if loop_summary else 0,
            "loops_processed": loop_summary.processed if loop_summary else 0,
            "bras_generated": len(bra_reports),
            "workspaces_failed": len(workspaces_failed),
            "dry_run": dry_run,
        },
        policy_level="auto",
        result="ok" if not workspaces_failed else "error",
        duration_ms=int((ended - started).total_seconds() * 1000),
    )

    # Idempotency marker is written even on dry_run so a real run can't
    # immediately retry on top of the dry one.
    _write_marker(last_run_marker_path, window_key)

    return CycleSummary(
        window_key=window_key,
        started_at=started_at_iso,
        ended_at=ended.isoformat(),
        dry_run=dry_run,
        skipped_idempotent=False,
        loop_summary=loop_summary,
        bra_reports=bra_reports,
        workspaces_failed=tuple(workspaces_failed),
    )


__all__ = [
    "DEFAULT_WINDOW_KEY_FORMAT",
    "DEFAULT_BRA_WINDOW",
    "CycleSummary",
    "run_nexus_cycle",
]
