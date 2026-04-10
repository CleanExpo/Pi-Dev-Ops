# Pi-SEO Monitor Agent — Specification

**Role:** Portfolio health intelligence layer. Interprets scan results over time, detects regressions, identifies systemic cross-repo patterns, generates remediation guidance for Tier 2-4 findings, and routes critical alerts through TriageEngine.

**Model:** `claude-sonnet-4-6`

**Responsibilities:**
1. Read latest scan results for all configured projects from `.harness/scan-results/`
2. Compare against previous monitor cycle (from `.harness/monitor-digests/`)
3. Detect regressions (≥5pt drop) and critical regressions (≥15pt drop)
4. Identify cross-repo systemic issues (same `scan_type:title` in 2+ repos)
5. Compute weighted portfolio health score (weights from `projects.json` `scan_priority`)
6. Generate remediation cards for Tier 2-4 findings using pi-seo-remediation skill
7. Route critical regressions and new `critical` findings through TriageEngine
8. Save digest to `.harness/monitor-digests/{YYYYMMDD-HHMM}.json`
9. Prune digests older than 30 days

**Dual Mode Operation:**

*Local mode* (no ANTHROPIC_API_KEY required):
- Loads and parses scan results
- Computes deltas, detects regressions, identifies systemic issues
- Calculates portfolio health score
- Generates alert list
- Saves structured digest JSON

*Agent mode* (ANTHROPIC_API_KEY present):
- Adds AI analysis layer on top of local computation
- Generates prose remediation guidance for Tier 2-4 findings
- Produces natural-language digest markdown with contextual recommendations
- Identifies non-obvious patterns (e.g. correlated failures across repos)

**Inputs:**
- Scan results: `.harness/scan-results/{project-id}/{date}-{scan_type}.json`
- Projects config: `.harness/projects.json`
- Previous digest: `.harness/monitor-digests/` (latest file)
- Optional: `project_id` to scope to a single project

**Outputs:**
- `MonitorDigest` JSON saved to `.harness/monitor-digests/{YYYYMMDD-HHMM}.json`
- Linear tickets via TriageEngine for critical alerts (unless `dry_run=True`)
- Logged summary to stdout

**Constraints:**
- Max 120s execution time
- Read-only access to scan results (never modifies scan files)
- Uses TriageEngine for all ticket creation (no direct Linear API calls)
- `dry_run=True` skips ticket creation and digest save (logs output only)
- Max 30 digest files retained (prune oldest when exceeded)

**CLI:**
```bash
python -m app.server.agents.pi_seo_monitor [--project PROJECT_ID] [--dry-run] [--use-agent]
```

**API trigger:**
```
POST /api/monitor  {"project_id": null, "use_agent": false, "dry_run": false}
GET  /api/monitor/digest
```

**Cron schedule:** 01:00, 07:00, 13:00, 19:00 UTC (1 hour after each scan cycle)

**Config reference:** `.harness/cron-triggers.json` type: `monitor`
