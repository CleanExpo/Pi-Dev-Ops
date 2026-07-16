"""Live judge-calibration runner — Prove-It Gate slice 3a (RA-7014).

Runs the binary judge N times over the expert-labelled calibration set and reports
judge↔expert disagreement + run-to-run flip-rate against the <20% bar. This is the
step that decides whether the gate may go blocking (slice 3b).

Requires a runnable model path (Anthropic OAuth token or ANTHROPIC_API_KEY +
claude_agent_sdk). Without one it exits 2 and measures nothing — it never fabricates
an agreement number.

    uv run python -m evals.run_calibration --runs 3
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

from evals.calibration import CalibrationCase, compute_calibration, format_report
from evals.judge import judge_binary, judge_binary_cli

_SET = Path(__file__).parent / "golden" / "intent_calibration.yaml"


async def _one_run(candidate: str, rubric: str, backend: str, sem: asyncio.Semaphore) -> "Verdict":
    from evals.judge import Verdict  # noqa: PLC0415
    async with sem:
        if backend == "cli":
            # judge_binary_cli is sync (subprocess) — run it off the event loop so the
            # semaphore actually parallelises across cases.
            return await asyncio.to_thread(judge_binary_cli, candidate, rubric)
        return await judge_binary(candidate, rubric)


async def _run(runs: int, backend: str, concurrency: int) -> int:
    data = yaml.safe_load(_SET.read_text())
    rubric, raw_cases = data["rubric"], data["cases"]
    sem = asyncio.Semaphore(concurrency)

    async def votes_for(c: dict) -> CalibrationCase:
        candidate = f'{{"message": {c["message"]!r}, "assigned_intent": {c["assigned_intent"]!r}}}'
        verdicts = await asyncio.gather(
            *[_one_run(candidate, rubric, backend, sem) for _ in range(runs)]
        )
        return CalibrationCase(
            case_id=c["id"], expert_pass=c["correct"], judge_passes=[v.passed for v in verdicts],
            _errors=[v.raw for v in verdicts if v.raw.startswith("judge-error")],
        )

    cases = await asyncio.gather(*[votes_for(c) for c in raw_cases])
    errs = [e for c in cases for e in c._errors]
    if errs:
        print(f"ABORT — judge not runnable ({len(errs)} errors): {errs[0]}", file=sys.stderr)
        return 2  # no model path; measure nothing rather than fake a number

    report = compute_calibration(cases)
    print(format_report(report))
    return 0 if report.calibrated else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3, help="judge runs per case (variance signal)")
    ap.add_argument("--backend", choices=["sdk", "cli"], default="sdk",
                    help="cli = `claude -p` (ambient auth, no token/SDK needed)")
    ap.add_argument("--concurrency", type=int, default=8, help="max parallel judge calls")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(_run(args.runs, args.backend, args.concurrency)))


if __name__ == "__main__":
    main()
