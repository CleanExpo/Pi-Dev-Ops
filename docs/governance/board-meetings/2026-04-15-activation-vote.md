# Board Meeting — 15 April 2026: Activation Vote

**Outcome:** Unanimous activation vote, subject to the locked conditions below.

## Conditions Locked

### 1. OB-4 — CARSI ADMIN_PASSWORD (OPS veto gate)

- **Status:** OPEN — developer action required.
- Full swarm activation remains blocked until the environment variable is set in the approved platform.
- **Ticket:** RA-950.

### 2. Rate limit — 3 autonomous PRs/day (CONTRARIAN)

- **Status:** IMPLEMENTED — `MAX_AUTONOMOUS_PRS_PER_DAY=3` in `swarm/config.py`.
- **Lift condition:** 20 consecutive green supervised merges.
- **Override:** `TAO_SWARM_MAX_DAILY_PRS` environment variable.

### 3. Merge RA-948 today (MARATHON)

- **Status:** PR #11 opened as `pidev/auto-0e474d30`.
- Human review and merge set the precedent for future autonomous PRs.

### 4. NotebookLM 5th criterion (ORACLE amendment)

- **Status:** IMPLEMENTED for RA-822, RA-823, and RA-824.
- Surface the top three open risks per entity from Linear and Pi-SEO evidence.

### 5. UPS purchase approved (board)

- **Budget:** Up to AUD 500.
- **Purpose:** Uninterruptible power for the Mac Mini swarm node.

This is a durable governance record migrated from the ignored runtime harness so clean checkouts and CI enforce the same locked decisions.
