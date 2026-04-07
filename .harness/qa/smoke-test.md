# Pi Dev Ops — Smoke Test Checklist

Run after every backend change. All items must pass before marking a Linear issue Done.

---

## Server Startup

```bash
python -m uvicorn app.server.main:app --host 127.0.0.1 --port 7777 --reload
```

- [ ] Server starts without import errors
- [ ] `[startup] Pi CEO ready.` printed to console
- [ ] `[persistence] Restored N session(s)` printed if prior sessions exist
- [ ] GC loop started (no error in startup logs)

---

## Authentication

```bash
# Login
curl -c cookies.txt -X POST http://localhost:7777/api/login \
  -H "Content-Type: application/json" \
  -d '{"password": "your-password"}'
# Expected: {"ok": true}

# Auth enforced
curl http://localhost:7777/api/sessions
# Expected: 401 Unauthorized

# Me endpoint
curl -b cookies.txt http://localhost:7777/api/me
# Expected: {"authenticated": true}
```

- [ ] Login returns 200 + sets `tao_session` cookie
- [ ] Unauthenticated request to `/api/sessions` returns 401
- [ ] Authenticated `/api/me` returns `{"authenticated": true}`

---

## Rate Limiting

```bash
# Send 31 rapid requests
for i in $(seq 1 31); do curl -s http://localhost:7777/api/me; done
```

- [ ] 31st request returns 429 Too Many Requests
- [ ] Rate limit resets after 60 seconds

---

## Build Session

```bash
curl -b cookies.txt -X POST http://localhost:7777/api/build \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/CleanExpo/Pi-Dev-Ops", "model": "sonnet"}'
# Expected: {"session_id": "...", "status": "created"}
```

- [ ] `/api/build` returns `session_id` and `status: "created"`
- [ ] `/api/sessions` shows the new session
- [ ] WebSocket `/ws/build/{sid}` streams phase output
- [ ] Session transitions through: created → cloning → building → evaluating → complete

---

## Evaluator Tier

- [ ] Build with `evaluator_enabled: true` shows Phase 4.5 in WebSocket output
- [ ] Evaluator output includes COMPLETENESS/CORRECTNESS/CONCISENESS/FORMAT lines
- [ ] `evaluator_score` populated in session JSON on disk
- [ ] OVERALL score and PASS/FAIL verdict visible in terminal

---

## Webhook

```bash
# Generate test HMAC (replace SECRET with TAO_WEBHOOK_SECRET value)
BODY='{"repository":{"html_url":"https://github.com/CleanExpo/Pi-Dev-Ops"},"ref":"refs/heads/main"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print "sha256="$2}')
curl -X POST http://localhost:7777/api/webhook \
  -H "x-github-event: push" \
  -H "x-hub-signature-256: $SIG" \
  -H "Content-Type: application/json" \
  -d "$BODY"
# Expected: {"triggered": true, "session_id": "..."}
```

- [ ] Valid webhook signature → session created
- [ ] Invalid signature → 401
- [ ] Missing signature header → 400

---

## Persistence

```bash
# Start a build, then restart the server
curl -b cookies.txt http://localhost:7777/api/sessions
```

- [ ] Restart server → prior completed sessions visible
- [ ] In-flight sessions marked `interrupted` on restart
- [ ] Session JSON files exist in `{TAO_LOGS}/sessions/`

---

## Garbage Collection

```bash
curl -b cookies.txt -X POST http://localhost:7777/api/gc
# Expected: {"removed": N, "orphans_removed": M, "errors": []}
```

- [ ] GC runs without error
- [ ] Old workspaces removed from `app/workspaces/`

---

## Lessons API

```bash
curl -b cookies.txt http://localhost:7777/api/lessons
# Expected: array of lesson objects

curl -b cookies.txt -X POST http://localhost:7777/api/lessons \
  -H "Content-Type: application/json" \
  -d '{"source":"smoke-test","category":"test","lesson":"Smoke test lesson","severity":"info"}'
```

- [ ] GET `/api/lessons` returns seed entries
- [ ] POST `/api/lessons` appends new entry
- [ ] Category filter works: `/api/lessons?category=persistence`

---

## Dashboard (Next.js)

```bash
cd dashboard && npm run dev
```

- [ ] `localhost:3000` renders without console errors
- [ ] Build form submits and receives session output
- [ ] Intent dropdown sends correct value to `/api/build`
