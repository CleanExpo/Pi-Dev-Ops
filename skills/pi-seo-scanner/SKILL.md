---
name: pi-seo-scanner
description: Scan interpretation specialist for Pi-SEO findings. Applies blast-radius scoring to prioritise findings, detects false positives, classifies into fix-now/schedule/suppress/investigate buckets, and recommends scan config changes per project.
---

# Pi-SEO Scanner Skill

Interpret scan results from the Pi-SEO autonomous scanner. Apply blast-radius scoring and classify each finding into an actionable bucket.

## Blast-Radius Score

```
blast_radius = severity_weight * exposure_factor * fixability_discount
```

**Severity weights:**
- critical → 4
- high → 3
- medium → 2
- low → 1

**Exposure factors** (from `projects.json` `deployments` field):
- Public-facing production URL present → 3
- Staging only → 2
- No deployments → 1

**Fixability discount:**
- `auto_fixable: true` → 0.7 (will be handled by autopr.py)
- `auto_fixable: false` → 1.0

Final score range: 0.7 – 12.0. Scores ≥ 9 are immediate escalations.

## Classification Buckets

| Bucket | Criteria | Action |
|--------|----------|--------|
| **fix-now** | blast_radius ≥ 9, OR severity=critical | Open Linear ticket Priority 1, trigger autopr if fixable |
| **schedule** | blast_radius 4–8.9 | Open Linear ticket Priority 2-3, add to sprint backlog |
| **suppress** | Confirmed false positive (see patterns below) | No ticket, log suppression reason |
| **investigate** | blast_radius < 4, insufficient context | Low-priority Linear ticket with investigation note |

## False Positive Detection Patterns

Suppress findings matching these patterns — they are structural characteristics of the codebase, not defects:

| Pattern | Scan type | Reason |
|---------|-----------|--------|
| `console.log` in `*.test.*` or `*.spec.*` files | code_quality | Test files are not production code |
| `eval(` in `next.config.*`, `webpack.config.*`, `vite.config.*` | security | Build-time eval is a bundler pattern |
| Secrets in `.env.example` or `.env.sample` | security | Example files contain placeholder values, not real secrets |
| `debug=True` in `conftest.py` or `pytest.ini` | security | Test configuration |
| `0.0.0.0` binding in Docker health-check commands | security | Container health probes bind to all interfaces by design |
| `print()` calls inside `if __name__ == "__main__":` blocks | code_quality | CLI entry points use print intentionally |
| `dangerouslySetInnerHTML` in `*Sanitized*`, `*Safe*`, `*Escaped*` components | security | Component name signals intentional sanitisation |

## Scan Config Recommendations

Evaluate per-project scan frequency based on health trend:

- Health score < 60 for 2+ consecutive scans → increase to 2-hour cycle
- Health score > 90 for 5+ consecutive scans → decrease to 12-hour cycle
- Critical finding detected → trigger immediate rescan after fix window (2h)
- Deployment event detected (new commit to main) → trigger deployment_health scan within 5 minutes

## Output Format

```json
{
  "project_id": "string",
  "scan_type": "security|code_quality|dependencies|deployment_health",
  "scored_at": "ISO-8601",
  "prioritised_findings": [
    {
      "fingerprint": "16-char hex",
      "title": "string",
      "severity": "critical|high|medium|low",
      "blast_radius": 9.0,
      "bucket": "fix-now|schedule|suppress|investigate",
      "file_path": "string",
      "line_number": 0,
      "auto_fixable": false,
      "suppression_reason": "string or null"
    }
  ],
  "recommended_actions": [
    {
      "type": "create_ticket|trigger_autopr|suppress|investigate",
      "finding_fingerprint": "string",
      "priority": "1|2|3|4",
      "notes": "string"
    }
  ],
  "scan_config_changes": [
    {
      "project_id": "string",
      "field": "scan_frequency_minutes",
      "current": 360,
      "recommended": 120,
      "reason": "string"
    }
  ],
  "false_positives": [
    {
      "fingerprint": "string",
      "pattern_matched": "string",
      "suppressed": true
    }
  ]
}
```
