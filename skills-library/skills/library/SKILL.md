---
name: library
description: Use when a task names an external service, API, MCP connector, CLI login or credential (Stripe, Supabase, Linear, OpenRouter, ElevenLabs, HeyGen and the like), before choosing how to reach it or deciding a credential is missing. Routes to connections.md, the registry of how each connection is reached and where its auth lives, never the values.
---

# Library: connection and credential routing

Read [connections.md](connections.md) first. It records, per connection, how to reach it
and where its auth lives. It never holds secret values, and none may be added to it.

1. Find the service in `connections.md` and use the route and auth location it names.
   If that route fails, follow the `connector-routing` skill's fallbacks.
2. On a machine with the full estate, resolve a credential with `~/.claude/bin/find-cred`
   before calling it absent. `INCOMPLETE` is not evidence of absence.
3. In a Cloudroom cloud sandbox, `bin/find-cred` and the local secret files do not exist.
   Use `room-cli secret request` or run the step on the founder's Mac with
   `room-cli mac run`. Cloudroom provides the `cloud-secrets` and `cloud-mac` skills
   that explain both, in cloud sandboxes only; they are not in this repo. Never copy
   keys into the sandbox, the transcript or source.
4. Before reproducing or handling a credential, read the `credential-custody` skill.

`connections.md` entries are dated observations. Re-check a status that matters before
relying on it.
