# Agent SDK Phase 2 — Canary Rollout Plan

_Created: 2026-04-11 (RA-574) | Owner: Phill McGurk_

---

## Overview

Phase 2 wired `claude_agent_sdk` into `sessions.py` generator and evaluator behind the `TAO_USE_AGENT_SDK` flag (RA-571/572). This document defines the staged rollout from 0% → 100% SDK, with kill criteria and sign-off gates at each phase.

The subprocess path (`claude -p`) stays in code through Phase C. Removal happens in Phase D (RA-576), gated on 7-day Phase C stability.

---

## Rollout Phases

### Phase A — Canary (10% SDK, target: 24h min)

**Activation:**
```bash
# Railway env — set via Dashboard or CLI:
TAO_USE_AGENT_SDK=1
```
At Phase A, the flag is either fully on or off. True 10% splitting requires a weighted random gate — see Phase A Split below.

**Phase A Split (optional, not required for Phase A start):**
Add to `_phase_generate()` before the SDK check:
```python
import random
use_sdk = config.USE_AGENT_SDK and random.random() < 0.10
```
This lets 10% of sessions hit the SDK path while 90% continue via subprocess. Remove the `random.random()` gate at Phase B.

**Kill criteria (any one = rollback immediately):**
- SDK error rate > 20% (check `.harness/agent-sdk-metrics/` — `success=false` rows)
- p95 generator latency increases by > 30% vs subprocess baseline
- Any session stuck in `building` status with SDK path that would have exited with subprocess
- Any sandbox violation or unexpected file write outside workspace

**Sign-off gate:** Run `python scripts/sdk_metrics.py` after 24h. Success rate ≥ 80%, p95 ≤ subprocess baseline × 1.3.

---

### Phase B — 50/50 Split (target: 48h min)

**Activation:** Remove the `random.random() < 0.10` gate. SDK path fires for all sessions when `TAO_USE_AGENT_SDK=1`.

*(Prerequisite: Phase A sign-off logged below.)*

**Kill criteria:**
- SDK error rate > 10%
- p95 generator latency > subprocess baseline × 1.2
- Any evaluator score regression: batch average drops > 0.5 points vs prior 48h

**Sign-off gate:** Review metrics for both Phase A and Phase B windows. Batch evaluator score comparison clean.

---

### Phase C — Full SDK (subprocess fallback still present)

**Activation:** Phase B sign-off → confirm `TAO_USE_AGENT_SDK=1` is the permanent Railway env setting.

*(Prerequisite: Phase B sign-off logged below.)*

**Kill criteria:**
- SDK error rate > 5% sustained over 6h
- Any production incident traceable to SDK path (root-cause confirmed)
- p95 evaluator latency > 180s (current subprocess baseline: ~120s)

**Sign-off gate:** 7 calendar days of clean metrics. Run `python scripts/sdk_metrics.py --all` — overall success rate ≥ 95%.

---

### Phase D — Subprocess Removal (separate ticket: RA-576)

**Prerequisite:** Phase C stable for 7 days. Sign-off below.

Removing `claude -p` fallback paths from `sessions.py`. Once done, `TAO_USE_AGENT_SDK` becomes a no-op (SDK is the only path) and can be removed from Railway env.

---

## Rollback Procedure

**Instant kill (no deploy needed):**
```bash
# Railway Dashboard → pi-ceo service → Variables → TAO_USE_AGENT_SDK → set to 0
# Restart service. Takes effect on next request.
```

**If Railway env change isn't fast enough:**
```bash
git revert HEAD && git push origin main   # triggers Railway redeploy
```

Rollback evidence: check `.harness/agent-sdk-metrics/` for the error spike that triggered rollback.

---

## Pre-Canary Checklist (must pass before Phase A opens)

Run these commands against a local server with `TAO_USE_AGENT_SDK=1`:

```bash
# 1. SDK path verification
python scripts/smoke_test.py --agent-sdk \
  --url http://127.0.0.1:7777 --password $TAO_PASSWORD

# 2. Full smoke suite against local server
python scripts/smoke_test.py \
  --url http://127.0.0.1:7777 --password $TAO_PASSWORD

# 3. Capture subprocess baseline metrics (before enabling SDK)
python scripts/sdk_metrics.py --all  # should be empty or show previous data
```

All must pass (exit 0) before opening Phase A.

---

## Metrics Baseline (capture before Phase A)

Run before enabling any SDK traffic:
```bash
# Capture subprocess baseline (TAO_USE_AGENT_SDK=0 or not set)
# Record p50/p95 generator latency for last 7 days from Railway logs
# Record evaluator score distribution from lessons.jsonl
```

Subprocess baseline (fill in before Phase A start):

| Metric | Baseline |
|--------|----------|
| Generator p50 latency | _TBD_ |
| Generator p95 latency | _TBD_ |
| Evaluator p50 latency | _TBD_ |
| Evaluator average score | _TBD_ |
| Build success rate (subprocess) | _TBD_ |

---

## Sign-Off Log

| Phase | Date | SDK success rate | p95 latency | Evaluator avg | Approved by |
|-------|------|-----------------|-------------|---------------|-------------|
| A | — | — | — | — | — |
| B | — | — | — | — | — |
| C | — | — | — | — | — |
| D | — | — | — | — | — |

---

## References

- RA-571: Generator SDK migration
- RA-572: Evaluator SDK migration
- RA-573: SDK metrics collection (`scripts/sdk_metrics.py`)
- RA-575: Smoke-test SDK path
- RA-576: Remove subprocess fallback (Phase D)
- `.harness/agents/sdk-version-policy.md`: SDK version and upgrade policy
