# Verifying KILL_SWITCH_SECRET is actually bound and accepted — design

**Why this exists.** After the hotfix deploy the secret was recorded as *inferred bound, not
observed*. A correctly-guarded route returns 401 whether the secret is bound-and-wrong or absent
entirely, so the two states are externally indistinguishable and no amount of unauthenticated
probing separates them. **A kill switch never proven to accept a valid credential is not a kill
switch** — by this estate's own rule, the first run of a new control is the failing one, and this
control has only ever been observed refusing.

## The discriminator

Verified against the deployed source (`origin/main`), the POST handler runs in this order:

1. `isAuthorisedMutation()` → **401** on failure
2. `op` validation → **400** if `op` is not `kill` or `resume`
3. `_baseUrl()` and the upstream call — **only after both**

So a request carrying the **correct** secret with an **invalid** op is authenticated, then
rejected on the op, and **returns 400 without ever reaching upstream.**

| response | meaning |
|---|---|
| **401** | secret rejected — unbound, or wrong. Deliberately indistinguishable; that is correct behaviour, not a limitation. |
| **400** | secret **ACCEPTED**. Auth passed; the request died on op validation. **This is the proof.** |

**Nothing can be killed or resumed by this probe.** `op=probe` fails validation before any
upstream call exists in the code path. The negative control is already observed: the same request
with no header returned 401 on production earlier today.

## The run — value never on screen, never in shell history

```bash
read -rs KS && \
curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST "https://pi-dev-ops.vercel.app/api/kill-switch?op=probe" \
  -H "content-type: application/json" \
  -H "x-kill-switch-secret: $KS" \
  -d '{}' ; unset KS
```

`read -rs` does not echo. The value reaches curl through a variable, so the expanded secret never
enters history. `unset` clears it from the session. **Expect `400`.**

## What I need from you

**The value, which nobody currently holds.** It was generated straight into Vercel through a pipe
and deliberately never read back — that was right at the time and is now the cost. Retrieve it
from the Vercel dashboard: *pi-dev-ops → Settings → Environment Variables → `KILL_SWITCH_SECRET`
→ reveal*. Paste it at the `read -rs` prompt. It never needs to reach me.

**TRAP, and it is the one that already caught us once today:** do **not** re-set the variable to
a value you choose and then probe. Vercel binds env per-deployment, so the running deployment
keeps the OLD value until a rebuild — the probe would return 401 and look like a failed
verification when it is actually a stale binding. If you do change it, **redeploy first, then
probe.**

## Then make it standing, because one proof covers one deployment

A kill switch verified once is verified for that deploy only. The honest upgrade: add
`KILL_SWITCH_SECRET` to GitHub Actions secrets and assert **400-with-secret / 401-without** as a
production smoke surface, so the switch is proven working on every deploy rather than once.

Cost: one more copy of the secret. Benefit: this stops being a thing we remember to check.
It is also a concrete instance of **Structural Limit 3's open half** — an expectation derived
from a *requirement* ("the kill switch must accept a valid credential") rather than from an
observed probe result. Recommended, but it is a founder call because it duplicates a secret.
