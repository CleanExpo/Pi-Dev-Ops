---
name: pi-seo-health-monitor
description: Portfolio health trend analyst for Pi-SEO. Reads scan history from .harness/scan-results/, detects regressions and sustained degradation, identifies cross-repo systemic issues, computes portfolio health score, and generates alert digests.
---

# Pi-SEO Health Monitor Skill

Analyse health trends across all monitored repos. Detect regressions, sustained degradation, and systemic cross-repo patterns. Generate portfolio health digests for operator review.

## Data Sources

All data is read from `.harness/scan-results/{project-id}/` — JSON files named `{date}-{scan_type}.json`.

Load the two most recent files per scan type per project for delta computation. Load up to 10 files per project for trend analysis.

## Portfolio Health Score

Weighted average across all projects, where weight = `scan_priority` from `projects.json`:

| scan_priority | Weight |
|---------------|--------|
| high | 3 |
| medium | 2 |
| low | 1 |

```
portfolio_health = sum(project.health_score * weight) / sum(weight)
```

Each project's `health_score` is the `overall` score from its most recent scan result (0-100, already computed by `ScanResult.health_score`).

## Regression Detection

Compare each project's current overall score against the previous scan cycle:

- **Regression**: score dropped ≥ 5 points between consecutive scans
- **Critical regression**: score dropped ≥ 15 points
- **Sustained degradation**: overall score below 70 for 3+ consecutive scans

Track per scan type as well as the overall composite.

## Systemic Issue Detection

A finding is systemic if the same `scan_type + title` combination appears in 2+ distinct repos within the same scan cycle. Systemic issues indicate a shared dependency, shared code pattern, or shared configuration problem.

Group findings by `scan_type:title` key across all current scan results. Any key with matches in ≥ 2 project IDs is systemic.

## Alert Thresholds

Generate an alert for each of the following:

| Condition | Alert type | Severity |
|-----------|------------|----------|
| Critical regression (≥15pt drop) | regression_critical | critical |
| New `critical` severity finding | new_critical | critical |
| Deployment health check failing | deployment_down | critical |
| Regression (5-14pt drop) | regression | high |
| Sustained degradation (< 70 for 3+ scans) | sustained_degradation | high |
| Systemic issue (2+ repos same finding) | systemic | medium |
| Portfolio health drops below 75 | portfolio_warning | medium |

## Digest Markdown Format

```markdown
# Pi-SEO Health Digest — {date}

**Portfolio Health: {score}/100** ({delta:+d} vs previous)

## Alerts ({count})
- 🔴 CRITICAL: {project_id} — {alert_description}
- 🟡 HIGH: {project_id} — {alert_description}

## Project Scores
| Project | Score | Delta | Trend |
|---------|-------|-------|-------|
| pi-dev-ops | 87 | +2 | ↑ stable |
| ...      | ... | ... | ... |

## Systemic Issues ({count})
- `{scan_type}:{title}` — affects {n} repos: {repo_list}

## Recommended Actions
1. {action}
```

## Output Format

```json
{
  "digest_timestamp": "ISO-8601",
  "portfolio_health": 82,
  "portfolio_delta": -3,
  "project_scores": {
    "pi-dev-ops": {
      "overall": 87,
      "by_type": {
        "security": 90,
        "code_quality": 85,
        "dependencies": 88,
        "deployment_health": 85
      },
      "delta": 2,
      "trend": "stable"
    }
  },
  "regressions": [
    {
      "project_id": "string",
      "scan_type": "string",
      "previous_score": 85,
      "current_score": 68,
      "delta": -17,
      "severity": "critical"
    }
  ],
  "systemic_issues": [
    {
      "key": "security:eval() usage",
      "scan_type": "security",
      "title": "eval() usage",
      "affected_projects": ["project-a", "project-b"],
      "count": 2
    }
  ],
  "alerts": [
    {
      "type": "regression_critical|new_critical|deployment_down|regression|sustained_degradation|systemic|portfolio_warning",
      "project_id": "string",
      "message": "string",
      "severity": "critical|high|medium"
    }
  ],
  "digest_markdown": "string"
}
```
