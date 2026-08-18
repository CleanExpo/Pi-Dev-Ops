# BLOCKER — GitHub Actions has not allocated a runner since 14 Aug

**Status:** open, founder-only. **Found:** 2026-08-18, overnight session.

## Bottom line

CI is not red because the code is broken. CI is red because **GitHub is refusing to
schedule jobs for this repository**. Every workflow — CI, Codebase Wiki, DESIGN.md lint,
morning_briefing, live_nexus_smoke, prove_it_evals, skills-drift-check — has failed
continuously since 2026-08-14T05:20Z, including scheduled runs as recent as
2026-08-17T12:30Z.

Nothing in the backlog can reach `main` until this is cleared, and no agent can clear it.
It needs a billing or infrastructure decision that only Phill can make.

## Evidence

Jobs are created and then killed before a machine is ever attached:

| Field | Value on every run since the cutover |
|---|---|
| `runner_id` | `0` |
| `runner_name` | `""` (empty) |
| `steps` | `[]` — no step ever executed |
| duration | 3–6 seconds |
| log archive | downloads as a valid but **empty** zip |

A CI job that installs Python and runs 3,224 tests cannot fail in 3 seconds. It never
started.

The cutover is sharp and visible in the run history:

```
2026-08-14T04:44:52Z -> 04:47:39Z  success   (2m47s — real runner)
2026-08-14T05:13:49Z -> 05:15:41Z  success   (1m52s — real runner)
2026-08-14T05:18:55Z -> 05:20:20Z  failure   Python/Ruff/Secrets/Frontend ALL SUCCEEDED
                                             on real runners; only the two smoke jobs,
                                             which needed a NEW runner at 05:20:15Z,
                                             were denied one
2026-08-14T06:08:28Z -> 06:08:35Z  failure   (7s — no runner for any job)
2026-08-14T06:23:48Z -> 06:23:54Z  failure   (6s — no runner for any job)
...
2026-08-16T21:07:44Z -> 21:07:49Z  failure   morning_briefing (5s)
2026-08-17T12:30:55Z -> ...        failure   live_nexus_smoke
```

Note the 05:18:55Z run especially: **the four jobs that already held runners all passed.**
That is the cleanest available proof that the code was fine and the capacity was not.

## Cause

Consistent with the GitHub Actions allowance for this repo being exhausted. This repo is
**private** and owned by a **User** account, so every Actions minute bills against the
2,000-minute monthly Free allowance, and GitHub bills per job **rounded up to a whole
minute** — a 7-second job costs a full minute.

This was already diagnosed in-repo. The RA-7222 commit message (1c4df736, the current tip
of `main`) states it directly:

> "Runners stopped being assigned at 05:20:15Z. Jobs since then fail in ~3s with
> runner_id: 0 and no steps, which reads as a broken build rather than an exhausted
> allowance — 12 red checks on a PR whose code was fine."

RA-7222 cut ~780 scheduled runs/month to reduce future burn. That reduces the *rate*; it
does not restore the *current* period's exhausted allowance, which is why runs are still
being denied four days later.

**Not directly confirmed:** the billing API needs the `user` OAuth scope, which the current
`gh` token does not carry (`gh auth refresh -h github.com -s user` would add it). So the
runner starvation is proven; the exhausted-allowance explanation is strongly supported by
the repo's own prior diagnosis and by the billing model, but the balance was not read.

## What is NOT broken

Every gate the CI workflow runs was reproduced locally at `main`'s tip, all green:

| CI job | Gate | Local result |
|---|---|---|
| Ruff lint | `ruff check app/` | All checks passed |
| Python | `pytest tests/` | 3,224 passed, 9 skipped, 2 xfailed |
| Python | `pytest swarm/` | 345 passed, 2 skipped |
| Python | `scripts/check_provisioning.py` | exit 0 |
| Python | `scripts/check_agent_registry.py` | PASS — 8 shadow agents |
| Secrets scan | `scripts/secrets_check.py` | PASS, no exposed secrets |
| Frontend | `npx tsc --noEmit` | exit 0 |
| Frontend | `npm run lint` | exit 0 |
| Frontend | `npm run build` | exit 0 — all routes built, incl. `/control` |

Production is also healthy and current:

- Railway backend `https://pi-dev-ops-production.up.railway.app/health` → **200** `{"status":"ok"}`
- Vercel frontend `https://pi-dev-ops.vercel.app` → **200**
- Latest Vercel **production** deployment is `READY` at `1c4df736` — the current tip of `main`

## Options — Phill's call

**RECOMMENDED: option 1 or 2 now, option 3 as a follow-up project.** Scoped 2026-08-18.

1. **Raise / enable the GitHub Actions spending limit.** Fastest restore. An earlier draft
   of this document framed the cost as significant; that was overstated. This repo's jobs
   are Linux (`ubuntu-latest`), which sits in the cheapest tier — realistically **cents per
   CI run, not dollars**. Caveat: GitHub's classic per-minute multipliers page now
   redirects, so that figure is a well-grounded estimate rather than a confirmed rate.
   Still a founder spend decision, but a far smaller one than first stated.
2. **Wait for the allowance to reset** at the next billing cycle. Free, but leaves the
   "always-on" pipeline dark until then, and the backlog accumulates behind it.
3. **Add a self-hosted runner** (e.g. the Mac Mini in the fleet). Confirmed on
   docs.github.com: *"GitHub Actions usage is free for self-hosted runners"* regardless of
   repo visibility — $0/minute permanently. Registered via `config.sh`, then
   `svc.sh install` runs it as a **launchd** service so it survives reboot.

   **Security, stated precisely.** GitHub's hardening guidance says self-hosted runners
   "should almost never be used for public repositories". For a PRIVATE repo the risk
   narrows but does not vanish: *anyone who can fork the repository and open a pull request
   (generally read access) can compromise the runner environment, including secrets and
   `GITHUB_TOKEN`*. This repo has no outside collaborators today, so present exposure is
   low — it grows the moment anyone gains read access. Mitigations are `--ephemeral`
   (fresh environment per job) and runner groups; bare-metal macOS cannot fully replicate
   GitHub-hosted VM isolation, so this is mitigation, not a guarantee.

   **Not a same-day fix.** Five workflows use `runs-on: ubuntu-latest` and would need
   retagging, and the suites carry Linux assumptions (paths, binary locations, possible
   case-sensitivity) — expect a session of compatibility work. `smoke-local` starts a live
   uvicorn server, which needs port-conflict thought on shared estate hardware.

Options 1 and 2 are a spend/timing decision. Option 3 trades a spend problem for an
operational-security one on founder hardware, and needs its own explicit call on ephemeral
mode and label scoping. Founder-only either way: the spend, the hardware exposure, and the
runner registration token.

## Side observation (separate, low priority)

Five `production` Vercel deployments in the recent history are in state `BLOCKED`, all of
them from `tao-codebase-wiki` bot commits (`docs(wiki): refresh per-directory WIKI.md
[skip ci]`). `[skip ci]` suppresses GitHub Actions but not Vercel, so each wiki refresh
still triggers a production deploy. Worth a ticket; not urgent, and not related to the
runner blocker.
