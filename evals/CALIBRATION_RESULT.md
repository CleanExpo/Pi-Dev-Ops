# Judge calibration result — Prove-It Gate (RA-7014 slice 3a→3b)

**Verdict: CALIBRATED — the judge may gate.** Measured 2026-07-08.

| Metric | Value | Bar |
|---|---|---|
| Cases | 30 (15 correct / 15 mislabelled) | — |
| Runs per case | 3 (90 judgments) | — |
| Judge↔expert disagreement | **0%** | < 20% |
| Run-to-run instability (flip) | **0%** | < 20% |

- **Judge:** `claude -p --model sonnet` (= claude-sonnet-5), the CLI backend
  (`evals/judge.py::judge_binary_cli`) — uses ambient Claude Code auth, so it runs
  without the Anthropic service token or `claude_agent_sdk`.
- **Command (reproducible):** `uv run python -m evals.run_calibration --backend cli --runs 3`
- **Set:** `evals/golden/intent_calibration.yaml` (intent_router 6-intent labels).

The judge agreed with every expert label on all three runs. Both calibration axes
clear the <20% bar decisively, so slice 3b (flip the gate to blocking) is unblocked
on the calibration criterion.

## Note on the service token (still worth provisioning)
This result was obtained via the CLI backend (ambient auth). The **always-on / CI /
Railway** path is headless with no interactive session, so it still needs the
long-lived token (`claude setup-token` → `sk-ant-oat01-*`, stored in 1Password
`Unite-Group-Infrastructure`). That token is an interactive OAuth step (founder-run);
it is NOT a blocker for the calibration above, which is already measured and green.
