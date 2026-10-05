---
name: reticle-verify
description: Drive the running app with Reticle and turn the result into Done evidence. Use after any UI, route or copy change in a repo that has `.reticle.json` (CARSI today), before calling the work done, before the PR release gate, or when asked "does it actually work in the browser" / "verify the flow" / "reticle". Combines the vercel:verification method (story, evidence, data flow, report) with Reticle's pass/fail verdicts, and gives donectl a command whose exit code is the proof.
updated: 2026-09-17
---

# reticle-verify

Reticle (open source, github.com/reticlehq/reticle) connects to a dev app through a small
in-page SDK. It clicks, reads the page and returns a verdict: `yes` (proved), `no`, or
`unknown`. **Unknown is never a pass.**

This skill runs Reticle **without registering it as a global MCP server**. The scripts talk
to the daemon over HTTP, so any agent on this machine can use it.

## When it fires (no need to be asked)

- Any change to a page, component, route, copy, or pricing in a repo with `.reticle.json`.
- Before writing "done", "fixed" or "verified" about UI behaviour.
- Before the `pr-release-gate` push step. The gate evidence goes in the PR body.

If the repo has no `.reticle.json`, say so and use `browser-routing` instead. Installing
Reticle into a new repo is a normal branch change and goes through the release gate.

## Step 1 — Say the story in one sentence

Take it from the diff (`git diff --name-only origin/main...HEAD`):
"A visitor on **[page]** does **[action]** and sees **[result]**." Every check below must
serve that sentence (vercel:verification, step 1).

## Step 2 — Bring up the two processes

Run both from the repo worktree, in the background:

```bash
NEXT_PUBLIC_GA_MEASUREMENT_ID= RETICLE_TELEMETRY=0 DO_NOT_TRACK=1 npx next dev -p 3917
RETICLE_TELEMETRY=0 DO_NOT_TRACK=1 npx -y @reticlehq/server@2.14.0 serve --headless --drive http://localhost:3917
```

- **Blank the analytics ID.** Otherwise the local `.env` sends dev visits to the live Google
  Analytics property. That request also never settles, so every drive reports "not settled".
- **Never use `.env.local` in CARSI.** It points at the live database pooler.
- The daemon listens on port 4400 (`RETICLE_PORT` overrides it). If Chromium is missing, run
  `node <npx cache>/playwright-core/cli.js install chromium-headless-shell`.

## Step 3 — Drive and save a flow (only when no saved flow covers the story)

Use `scripts/reticle-mcp.mjs`. It takes a JSON list of `[tool, args]`. Tools Reticle does
not advertise go through `["reticle_run", {"tool": "...", "args": {...}}]`.

1. **Get your own tab.** Call `reticle_lease {action:"acquire", url}` and use its `sessionId`.
   A shared tab gets throttled.
2. **Find the element.** Call `reticle_query {sessionId, by:"text", value:"..."}` to get its role and name.
3. **Act and check.** Call `reticle_act_and_wait {sessionId, target:{role,name}, action:"click", until:{...}}`.
   Only this call and `reticle_assert` return verdicts.
4. **Write the flow file.** Save it at `.reticle/flows/<projectId>/<name>.json`.
   - Use **keyed** checks. Saved flows accept only
     `text {contains, visible, absent}`, `element {role, name, testid}`, `net`,
     `console {level, absent}`, `signal` and `state`.
   - `{kind:"route"}` and `{kind:"settled"}` inside an `allOf` are **dropped without warning**.
     `reticle_flow {action:"load"}` shows what actually survived.
5. **Avoid client-side page changes as a flow step on Next 16 dev.** The router's `_rsc`
   redirect fetch looks like it never ends, so replay reports drift.
   - Instead, set `startPath` to the target page and act on something on that page, such
     as an FAQ toggle.
6. **Release the tab.** Call `reticle_lease {action:"release"}`.

Commit `.reticle/flows/**`. Keep `capsules/`, `impact.json`, `intent.json`, sessions and runs
out of git: they hold page data and machine state.

## Step 4 — Run the gate (this is the evidence)

```bash
node ~/.claude/skills/reticle-verify/scripts/reticle-gate.mjs \
  --repo <worktree> --app-url http://localhost:3917/ --self-test --evidence <file.json>
```

| Exit | Verdict | Meaning |
|---|---|---|
| 0 | PROVEN | Reticle said `yes`, no flow failed, the tree is clean, so the evidence binds to HEAD |
| 1 | FAILED / UNBOUND / GATE_BLIND | a flow broke; or uncommitted changes; or the planted false check passed |
| 2 | UNPROVEN | the app or daemon is down, or there are no saved flows. This is not a pass |

- `--self-test` copies a flow, makes its text check impossible, and requires the replay to
  fail. **Use it on the first run of every session.** A gate that cannot fail proves nothing.
- The report lists `unknownProvenance` (flows re-run because Reticle cannot map them to
  source files) and `undrivenControls`. **Quote both.** "1 flow passed, 53 controls undriven"
  is the honest size of the claim.

### Wire it into Done

Put the gate in a donectl criterion as the `recipe`. donectl runs it and uses the exit code
as the proof:

```json
{"id": "C-ui", "statement": "Pricing still tells visitors yearly membership cannot be bought yet",
 "recipe": "node ~/.claude/skills/reticle-verify/scripts/reticle-gate.mjs --repo . --app-url http://localhost:3917/"}
```

The recipe needs the dev server and daemon running (Step 2). If they are down it exits 2,
so donectl reports FAILED rather than a false green.

## Step 5 — Report (vercel:verification format)

- **Story:** the one sentence.
- **Flow status:** one row per boundary (UI renders, action, result shown, console), each
  with the Reticle evidence.
- **Stop at the first broken boundary.** Quote the drift `reason` and the `consequence` line,
  then fix it.
- **Always name:** the head SHA, the gate verdict and exit code, and the self-test result.

## Traps measured on CARSI (17/09/2026)

- A local `/courses` fails without a database (ECONNREFUSED). Pick flows that do not need data,
  or point the dev app at a local database.
- `reticle verify` (the CLI) binds port 4400 itself, so it clashes with a running daemon. Use
  the scripts here instead.
- Running `reticle init` globally, or turning off telemetry through its config, is blocked on
  this machine. Use `--no-mcp --files-only` and the environment variables above.
- The dev server rewrites `next-env.d.ts` on every start. Run
  `git checkout -- next-env.d.ts` before the gate, or it reports UNBOUND.

## Not covered yet

- **Automatic triggering.** A hook that runs the gate on its own needs a Bash permission rule
  from Phill. Until then this skill fires by routing, not by force.
- **Production.** The SDK is dev-only, so this never verifies a deployed site. Use
  `vercel-prod-debug` or `browser-routing` for that.
