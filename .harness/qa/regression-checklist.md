# Pi Dev Ops — Regression Checklist

Scenarios that have burned us before. Check these after any change to `sessions.py`, `auth.py`, `persistence.py`, or `main.py`.

---

## Session Persistence

- [ ] **Corrupt session file on crash:** Write a session JSON, crash mid-write (simulate with kill -9), verify old file is intact (atomic write guarantee)
- [ ] **Path traversal via session ID:** Session ID containing `../` should be sanitised to alphanumeric only. File must not be created outside `{TAO_LOGS}/sessions/`
- [ ] **Restore interrupted sessions:** Restart server with a session in `building` state → verify it's marked `interrupted`, not left as `building`

## Rate Limiting

- [ ] **Memory leak regression:** Run 100 requests from 50 different IPs, wait 3 minutes, verify `_req_log` purges stale IPs. Dict size should shrink back toward 0.
- [ ] **Rate limit bypass via IP spoofing:** `X-Forwarded-For` header should not bypass rate limiting (rate limit is keyed on real socket IP via `request.client.host`)

## Authentication

- [ ] **Expired token rejection:** Manually expire a session token (edit `SESSION_TTL` to 1s), verify subsequent requests return 401
- [ ] **Timing attack resistance:** Verify `verify_session_token` uses `hmac.compare_digest` (not `==`) for signature comparison

## Build Pipeline

- [ ] **Clone failure → clean status:** If `git clone` fails, session status must be `failed` (not stuck at `cloning`)
- [ ] **Claude not in PATH:** If `claude` binary missing, Phase 3 returns error, session fails cleanly (not a Python exception crash)
- [ ] **Workspace already exists:** If `app/workspaces/{sid}/` already exists (orphan from prior run), build must not silently reuse it — must re-clone or validate it

## Evaluator

- [ ] **Unparseable evaluator output:** If evaluator returns malformed text (no OVERALL line), `evaluator_status` = `"error"`, build still proceeds to push
- [ ] **Evaluator timeout:** If evaluator takes >120s, `evaluator_status` = `"timeout"`, build still proceeds
- [ ] **Phase numbering consistency:** When evaluator disabled, phases show [1/5]...[5/5]; when enabled, [1/6]...[6/6]

## Webhook

- [ ] **Replay attack:** Sending the same signed payload twice should create two sessions (no deduplication yet — acceptable, but document it)
- [ ] **Missing WEBHOOK_SECRET:** If `TAO_WEBHOOK_SECRET` not set, endpoint returns 500 (not 401 or 200)
- [ ] **Linear webhook with no repo label:** `parse_linear_event` returns None when no `repo:<url>` label → `{"skipped": true}` response

## Garbage Collection

- [ ] **GC does not delete active workspaces:** Sessions in `building` or `evaluating` state must never have their workspace deleted by GC
- [ ] **Orphan detection:** Dir in `app/workspaces/` with no matching session in `_sessions` → removed after GC_MAX_AGE

## CORS / Security Headers

- [ ] **X-Frame-Options: DENY** present on all responses
- [ ] **CSP header** present and does not include `unsafe-eval`
- [ ] **SameSite cookie**: `strict` locally, `none` + `secure` on Railway
