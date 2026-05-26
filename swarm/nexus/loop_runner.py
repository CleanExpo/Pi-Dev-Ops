"""Driver that walks every due loop and runs its cycle.

Phase B / B3. Stays pure — the only I/O is delegated to the injected
LoopsStore, OutcomesStore, LLM and Clock. Schedulers (Hermes cron,
launchd) call run_due_loops() on a tick; the runner has no concept of
time except via the injected clock.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from .discovery_loop import (
    ClockProtocol,
    CycleResult,
    LLMProtocol,
    LoopsStore,
    RunSummary,
    run_discovery_cycle,
)
from .outcomes import OutcomesStore

log = logging.getLogger("pi-ceo.nexus.loop_runner")


def run_due_loops(
    *,
    loops_store: LoopsStore,
    outcomes_store: OutcomesStore,
    llm: LLMProtocol,
    clock: ClockProtocol,
) -> RunSummary:
    """Process every loop currently due. Returns a RunSummary; never raises."""
    now = clock.now()
    try:
        due = loops_store.list_due(now=now)
    except Exception as exc:  # noqa: BLE001
        log.warning("loop_runner list_due failed (non-fatal): %s", exc)
        return RunSummary()

    summary_results: list[CycleResult] = []
    ok = skipped = llm_errors = cost_capped = invalid_cadence = 0

    for loop in due:
        if loop.loop_kind != "discovery":
            # Phase B/B3 only implements discovery; future loop kinds
            # plug in here as separate dispatchers.
            continue
        result = run_discovery_cycle(
            loop,
            llm=llm,
            outcomes_store=outcomes_store,
            clock=clock,
        )
        summary_results.append(result)

        if result.result == "ok":
            ok += 1
        elif result.result == "no_outcomes":
            skipped += 1
        elif result.result == "llm_error":
            llm_errors += 1
        elif result.result == "cost_capped":
            cost_capped += 1
        elif result.result == "invalid_cadence":
            invalid_cadence += 1

        # Always advance next_run_at except when cadence itself was bad.
        if result.result != "invalid_cadence" and result.next_run_at:
            updated = replace(
                loop,
                last_run_at=now.isoformat(),
                next_run_at=result.next_run_at,
            )
            try:
                loops_store.save(updated)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "loop_runner save failed (non-fatal) loop=%s err=%s",
                    loop.id, exc,
                )

    return RunSummary(
        processed=len(summary_results),
        ok=ok,
        skipped_no_outcomes=skipped,
        llm_errors=llm_errors,
        cost_capped=cost_capped,
        invalid_cadence=invalid_cadence,
        cycle_results=summary_results,
    )
