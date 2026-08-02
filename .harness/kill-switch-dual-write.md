# `KILL_SWITCH_SECRET` — generate once, dual-write, never handled

Replaces the two-paste procedure that caused the transcript exposure. One freshly generated
value goes into both stores in a single command. **It never surfaces in either direction and
nobody ever holds it.** Costs one extra rotation, which is free.

---

## Create this in GitHub FIRST — the command needs somewhere to write

`gh secret set --env` fails if the Environment does not exist, so this is a prerequisite, not a
follow-up.

**Settings → Environments → New environment**

1. **Name:** `kill-switch-proof` (exact — the workflow declares this string)
2. **Deployment branches and tags:** change from the default *All branches* to
   **`Selected branches and tags`**, then **Add deployment branch or tag rule** → `main`

   *Not* "Protected branches only" — that happens to be equivalent today because `main` is the
   only protected branch, but it silently widens the moment another branch is protected. Name the
   branch.

3. Leave required reviewers and wait timer **off**. They gate deployments; this is a read-only
   probe, and a review prompt on every run makes the check something people learn to click past.

**Do not add the secret through the UI.** The command below writes it.

---

## The command — run once

```bash
KS="$(node -e 'console.log(require("crypto").randomBytes(32).toString("hex"))')" && \
printf '%s' "$KS" | vercel env add KILL_SWITCH_SECRET production --force && \
printf '%s' "$KS" | gh secret set KILL_SWITCH_SECRET --env kill-switch-proof --repo CleanExpo/Pi-Dev-Ops && \
unset KS && echo "dual-write complete — value never surfaced"
```

Run it from `D:\Pi-Dev-Ops\dashboard` so the Vercel project link resolves.

**Why each piece:**

- **`KS="$(...)"`** — the value lives in a shell variable for two commands, never printed. The
  command line itself contains no secret, so shell history holds nothing.
- **`printf '%s'`** rather than `echo` — **no trailing newline.** The route trims its side, but
  the GitHub secret would keep a newline and the header comparison would fail. This is the kind
  of detail that produces a 401 and looks like a broken rotation.
- **`--force`** overwrites the existing Vercel value without prompting.
- **`&&` throughout** — if the Vercel write fails, the GitHub write does not run, so the two
  stores cannot silently diverge. Divergence here is the worst outcome: the probe would fail
  while the switch actually works, or vice versa.
- **`unset KS`** clears it from the session.

---

## Then redeploy — before any verification

```bash
vercel --prod
```
or push any commit to `main`.

**Env binds per-deployment.** The running deployment keeps the OLD value until a new build, so
probing before redeploying returns 401 and looks exactly like a failed rotation. This has already
cost time once today.

---

## Order of operations

1. Create the Environment with the branch policy
2. Run the dual-write command
3. Redeploy
4. Merge #604
5. The workflow runs on push to `main` — report all three results

---

## What to watch when it runs

Three results, and **the negative controls passing is what makes the 400 evidence** rather than a
green tick:

| # | Job / assertion | Pass condition |
|---|---|---|
| 1 | `accepts-valid-credential` — correct secret, invalid op | **400** (401 means unbound or a stale deployment) |
| 2 | Same job, negative control — no secret | **401** (a route returning 400 to everyone would otherwise satisfy #1) |
| 3 | `secret-is-not-repo-wide` — job omits `environment:` | secret resolves **empty** (if it resolves, it was added at repo/org scope) |

Plus the **branch-policy control**, run once by hand: dispatch the workflow from a non-`main` ref.
**Expected: `accepts-valid-credential` never starts**, and GitHub reports *"Branch is not allowed
to deploy to kill-switch-proof due to environment protection rules"*. **The job being blocked is
the pass.** If it runs and resolves the secret, the branch policy is missing and every pushable
branch can read the live kill switch.
