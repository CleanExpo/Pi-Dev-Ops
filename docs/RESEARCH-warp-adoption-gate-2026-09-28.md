# Research: Warp adoption gate (28/09/2026)

**Verdict: DEFER the platform, ADOPT four patterns into the mesh.**

**Why this exists:** Phill asked what Warp (warp.dev) and its public factory (build.warp.dev) could add
to Pi-Dev-Ops and Mission Control. The Mission Control intent v7 says any outside runtime must pass an
adoption gate before it becomes load-bearing:

- L611: observe → verify the source → find the gap → shadow → red-team → compare → adopt, defer or reject.
- L4608 and L4621: no load-bearing dependency without benchmark, data-policy, cost and reversibility evidence.

This file is that gate's record.

**Sources:** every product claim below comes from a page fetched on 28/09/2026. A vendor product can
change within weeks. Re-fetch before relying on any row.

## 1. What Warp is now

| Capability | How it's reached | Source |
|---|---|---|
| Cloud agents ("Automation Platform", formerly "Oz"; the Oz name ends 06/10/2026) | REST `https://app.warp.dev/api/v1`: `POST /agent/run`, `GET /agent/runs`, `GET /agent/runs/{id}`, follow-ups, cancel. States: QUEUED / INPROGRESS / SUCCEEDED / FAILED | docs.warp.dev/platform/overview, docs.warp.dev/reference/api-and-sdk |
| SDKs and CLI | Python (`oz-sdk-python`), TypeScript, `oz agent run` | same |
| Triggers | Slack, Linear, Jira, GitHub, GitHub Actions, GitLab, Bitbucket, Azure DevOps, cron, API, webhooks | docs.warp.dev/platform/overview |
| Linear flow | Assign or mention `@warp`. The agent posts activity and a live session link on the ticket, opens a PR, and posts the PR link back | docs.warp.dev/platform/integrations/linear |
| Environments | A Docker image plus repos to clone plus setup commands | docs.warp.dev/platform/overview |
| Harnesses | Warp Agent (default), Claude Code, Codex | same |
| Harness auth | Claude Code requires an Anthropic (or Bedrock) **API key**. "A ChatGPT subscription … does not include API access" | docs.warp.dev/platform/harnesses/authentication |
| Factories (Early Access) | Factories as code; Factory API (`POST /factory/{uid}/runs` to a "foreman agent"); Factory MCP | docs.warp.dev/factories, …/factory-api |
| Self-hosted workers | **Enterprise only.** Transcripts and prompts still transit Warp's control plane | docs.warp.dev/platform/self-hosting, …/factories/infrastructure-and-security |
| Warp Drive (workflows, notebooks, prompts, rules) | GUI sharing. No API documented (UNCONFIRMED) | docs.warp.dev/knowledge-and-collaboration/warp-drive |
| Open source | The terminal client is AGPL v3 (github.com/warpdotdev/warp). The platform is proprietary | warp.dev/blog/warp-is-now-open-source |
| Pricing | Free (BYO inference, limited cloud agents), Build $20/mo, Max $200/mo, Business $50/user/mo, Enterprise custom. Platform credits are billed per agent-hour; the rate per hour is UNCONFIRMED | warp.dev/pricing, docs …/platform-credits |

**build.warp.dev is not a live agent feed.** It is a public kanban over the open-source repo's issues:

- Counts per stage: Triaging, Ready to spec, Creating spec, Ready to implement, Implementing, Reviewing,
  Closed.
- Each issue carries a "who is it waiting on" label: agent, contributor, review, maintainer, needs-info.
- Each issue shows its PR.

Warp describes it as "a factory queue running in public".

## 2. Gate result

| Gate step | Result |
|---|---|
| Gap | Real, and on our side: the mesh keeps no run transcript, records no run outcome, sends Linear no feedback, has no factory-style board, and cannot be launched with a brief. See §3 |
| Second orchestrator? | **Yes.** Warp dispatches, holds run state and owns triggers. Intent L4599 forbids a new orchestrator above Mission Control, and L93 says extend rather than create |
| Cost | Our fleet runs `claude -p` on flat-rate Max subscriptions. On Warp, Claude Code needs a metered API key plus agent-hour credits. That is new spend authority, which intent L452-465 and L4619 do not grant |
| Data | Below Enterprise, runs execute in Warp's cloud. At every tier, code context in transcripts and prompts passes through Warp's control plane |
| Reversibility | Good in principle, since the API is thin, but there is nothing to reverse if we never make it load-bearing |
| **Decision** | **DEFER.** No account, key, trial or spend |

**Revisit when either of these happens:**
1. Warp's harnesses accept a subscription login (Claude Max / ChatGPT) instead of an API key.
2. Self-hosted workers stop sending transcripts through Warp at a non-Enterprise tier.

## 3. Patterns adopted instead (each its own ticket and PR)

Tickets: 1 = UNI-2796, 2 = UNI-2797 (blocked by UNI-2796), 3 = UNI-2798, 4 = UNI-2799.

| # | Warp pattern | Our gap (at 9eca38cb) | Where it lands |
|---|---|---|---|
| 1 | Run list with state, logs and a session link | `mesh/runner.py` `run_claim` starts the agent with no output capture, and `mesh_work_claims` has no run id, duration, exit code or error | `mesh/run_record.py` (new), `mesh/runner.py`, `mesh/schema/0002_*.sql`, `app/server/routes/mesh.py` claim/update |
| 2 | Linear: activity on the ticket, PR link back | A claimed ticket moves to In Progress and nothing else is said | the claim/update handler posts a Linear comment through the existing server Linear client |
| 3 | build.warp.dev stage counts plus "waiting on agent / human" | Neither the Live Wall nor `/control` shows the queue that way | a new `/control/factory` section inside the existing dashboard, behind login |
| 4 | Launch a run with a prompt | A dispatched claim arrives without a brief, and the runner refuses it (`runner.py:121-129`) | dispatch attaches the Linear title and description |

**Not adopted:** job sandboxing (gap 6). It is real, but it is ours to solve with the existing
`app/server/sdk_execution_boundary.py`, not a Warp pattern. It gets a separate ticket.

**Publishing:** a public version of the factory board would need Phill's publishing decision. Intent
L4619 says publishing is not authorised, and L1765 says publish only verified proof. Pattern 3 ships
internal-only.

## 4. Tech-radar entry (intent L1379: "managed/long-horizon agent runtimes")

| Item | Ring | Reason | Re-check |
|---|---|---|---|
| Warp Automation Platform / Factories | **Hold** | Second orchestrator, metered-only harness auth, and transcripts leave our machines | On either revisit trigger in §2, or 28/12/2026, whichever comes first |
| Warp terminal (AGPL client) | Assess (individual use only) | A personal tool choice. It carries no fleet authority | — |
