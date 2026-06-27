# Session Handoff

## 1. Summary of what was done

## 2. Where it started

## 3. Decisions locked + what shipped

### Decisions locked

| Decision | Reason | Evidence |
|---|---|---|

### What shipped

| Item | Branch | Commit | Files | Verification |
|---|---|---|---|---|

## 4. Key files

| File | Status | Why it matters | Next owner |
|---|---|---|---|

## 5. Running state

| Area | State | Evidence | Risk |
|---|---|---|---|

## 6. Verification — how to confirm things still work

### Backend

```bash
python -c "from app.server.main import app"
python -m pytest tests/ -x -q
```

### Dashboard

```bash
cd dashboard
npx tsc --noEmit
npm run build
```

### Smoke

```bash
python scripts/smoke_test.py --url http://127.0.0.1:7777 --password $TAO_PASSWORD
```

### Command checks

```text
/session-handoff
$session-handoff
```

## 7. Deferred + open questions

### Deferred

| Item | Owner | Blocking? | Why deferred |
|---|---|---|---|

### Open questions

| Question | Owner | Blocking? | Why it matters |
|---|---|---|---|

## 8. Pick up here

```text
Start here:
1.
2.
3.

Do not redo:
-

First command to run:
<command>
```

## 9. Risk notes

## 10. Handoff quality check

- [ ] Completed vs deferred is clear
- [ ] Shipped vs local-only is clear
- [ ] Verification is not faked
- [ ] Next command is explicit
- [ ] No unresolved blocker is hidden
