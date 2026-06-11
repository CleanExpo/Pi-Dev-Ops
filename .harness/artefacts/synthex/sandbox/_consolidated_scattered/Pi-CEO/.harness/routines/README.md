# .harness/routines/

This folder contains **Claude Code Routine** definition files for the Pi-Dev-Ops harness.

---

## What are Claude Code Routines?

Claude Code Routines are **cloud-hosted, autonomous agent tasks** that run without a local Mac dependency. They are registered in the Claude Code web interface (or via API) and can be triggered by:

| Trigger type      | Description                                                              |
| ----------------- | ------------------------------------------------------------------------ |
| **GitHub event**  | Fires on a push, pull request, or release event in a connected repo      |
| **Schedule**      | Runs on a cron expression (e.g. daily health sweep)                      |
| **API trigger**   | Called programmatically via a signed POST to the Routine's webhook URL   |

Routines have access to configured secrets (env vars), can call external APIs via `fetch()`, and post results back to the Pi-CEO Railway backend via the `/api/webhook/routine-complete` endpoint.

Reference: [Claude Code Routines — concepts](https://docs.anthropic.com/en/docs/claude-code/routines)

---

## How to register a Routine

1. Open the Claude Code settings (cloud dashboard or `claude routines` CLI).
2. Create a new Routine and paste in the script from the relevant `.md` file below.
3. Set the trigger (GitHub event / schedule / API).
4. Add all required secrets listed in the definition file.
5. Activate the Routine.

---

## Routine index

| File                           | Ticket  | Trigger type   | Trigger detail                          | Purpose                                    |
| ------------------------------ | ------- | -------------- | --------------------------------------- | ------------------------------------------ |
| `SYN-694-deploy-verify.md`     | SYN-694 | GitHub event   | `push` on `CleanExpo/Synthex:main`      | Poll Vercel + health-check Synthex deploy  |
