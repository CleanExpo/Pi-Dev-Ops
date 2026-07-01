# Improvement Proposal: Rate Limit

**Generated:** 2026-07-01  
**Source:** lessons.jsonl — 2 entries (2 warnings)  
**Proposed action:** Add a CLAUDE.md section  
**Target:** CLAUDE.md section: `## Rate Limit Guidelines`

## Recurring Lessons (2 occurrences)

- ⚠️ **[architecture-review]** _req_log in auth.py accumulates IP keys forever if never cleaned up. Prune stale IPs (last request >120s ago) every 5 minutes inline inside check_rate_limit() — no background task needed in asyncio.
- ⚠️ **[RA-1043-1049-review]** In Railway deployments, request.client.host is the internal load-balancer IP which may vary per LB instance. A per-IP rate limiter keyed on request.client.host never fills up. Trust X-Forwarded-For in cloud environments (RAILWAY_ENVIRONMENT set) — Railway strips any client-supplied XFF before injecting the real client IP so this cannot be spoofed.

## Proposed Content

Add the following section to CLAUDE.md:

```markdown
## Rate Limit Guidelines

- _req_log in auth.py accumulates IP keys forever if never cleaned up. Prune stale IPs (last request >120s ago) every 5 minutes inline inside check_rate_limit() — no background task needed in asyncio.
- In Railway deployments, request.client.host is the internal load-balancer IP which may vary per LB instance. A per-IP rate limiter keyed on request.client.host never fills up. Trust X-Forwarded-For in cloud environments (RAILWAY_ENVIRONMENT set) — Railway strips any client-supplied XFF before injecting the real client IP so this cannot be spoofed.
```

## Review Required

This proposal was auto-generated. A human must review and apply it.
Close this Linear ticket when applied or explicitly rejected.