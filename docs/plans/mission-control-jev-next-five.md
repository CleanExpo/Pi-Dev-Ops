# JEV research and Mission Control's next five priorities

> Integration update, 2026-09-19: the owner approved completion and delivery of the 143-file shelf onto current Main. Active branch: `feat/mission-control-readiness-integrated`, based on `2ca26817`. Earlier branch names, counts and completion statements below are historical. Current evidence is in `mission-control-readiness-verification.md`. The next five remain deferred until this delivery is verified.

> Shelf audit update: the original ranking was based on the old readiness checkout. Fresh Main `d4dafa53` already contains recovery leases/checkpoints, typed routing and Live Wall. Keep the five objectives, but implement integration gaps using these foundations. See `.harness/shelf-audit-2026-09-19.md`; do not start duplicate engines from this older snapshot.

Research date: 2026-09-19. These are recommendations after completion of the original five; no JEV account, API key, paid call, dependency or external integration was created.

## What is publicly verified

TypeSafe announced Jev on 15 September 2026 in early access. It evaluates supplied state against bounded questions and returns decisions for software. The launch claims about speed and efficiency are vendor evaluations, not measurements on Mission Control. [TypeSafe launch](https://typesafe.ai/blog/introducing-system-one-models-and-jev).

The documented primitives are Choice, Score and Noul (a yes/no probability). They support narrow decisions such as selecting a handler or judging a condition. They do not replace the models that write code, plans and explanations. [Official introduction](https://docs.typesafe.ai/introduction).

Vercel announced access through AI Gateway on 16 September, using `typesafe-ai/jev` and an experimental evaluation API. Public documentation and an integration therefore exist alongside TypeSafe's direct early-access rollout. [Vercel announcement](https://vercel.com/changelog/typesafe-ai-jev-now-available-on-ai-gateway).

TypeSafe lists input pricing of $42 per billion tokens ($0.042 per million); the Gateway model page displays approximately $0.04 per million. This is metered API usage, not an established entitlement under the user's Claude/ChatGPT subscriptions. Current subscription-only policy must continue to deny it. [TypeSafe pricing](https://typesafe.ai/), [Gateway model page](https://vercel.com/ai-gateway/models/jev).

The vendor documents wrong answers involving arithmetic, dates, indirection, irrelevant context and adversarial input. A valid output type does not establish factual correctness or authority to act. Keep exact calculations, permissions, budgets and delivery gates in deterministic code. [Known model limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13).

## The most relevant idea for this ecosystem

TypeSafe's skill-selection example uses a large Hermes skill catalog in two stages: rank candidates, then inspect a shortlist and allow rejection of every candidate. Only the selected skill is introduced to the working agent. This directly fits the earlier skill-context overflow problem. Its reported improvement comes from the vendor's demonstration, not this repository. [Official skill suggestion example](https://docs.typesafe.ai/cookbooks/skill_suggestion).

Apply that architecture using the existing permitted local/subscription routes: searchable capability metadata outside the prompt, a small task-specific shortlist, full instructions loaded only on selection, and an explicit no-match result. JEV can be evaluated later as an optional decision provider if access, spend and data handling are explicitly authorized. It should first run in observation-only mode against historical labelled missions; measure routing mistakes, abstention, latency and cost before allowing actions.

## Ranked next five

The user's target is a single place to assign an outcome and have the ecosystem execute it autonomously. Coverage means every built capability is registered, reachable, tested and available when relevant to a mission.

| Priority | Enhancement | Existing foundations to extend | Proof of completion |
| --- | --- | --- | --- |
| 1 | A durable mission lifecycle from goal to verified result. One mission ID follows planning, execution, review, recovery and delivery; reconnecting or restarting resumes the same mission. | `goal_ticket.py`, `spec_pipeline/`, `orchestrator.py`, `persistence.py`, dashboard Build/control flow | Start from the dashboard, disconnect it, restart a worker and resume without losing scope or duplicating an external action; final evidence stays attached to that mission. |
| 2 | A complete capability registry with on-demand skill/tool loading. Track configured, reachable, authorized and successfully exercised separately. Route only the relevant tools/instructions into each step. | `/api/capabilities`, `dashboard/lib/command-centre/tools/catalogue.ts`, current skill discovery and integration health | Every supported ecosystem capability maps to a callable adapter and contract test. Hundreds of installed skills do not inflate startup context. Missing/unavailable capabilities give a specific blocker. |
| 3 | Typed decisions for routing and next actions. Use bounded choices such as execute, retry, repair, gather evidence or escalate, with recorded evidence and an abstain outcome. | Shared provider router, brief/triage logic, tool gate, release/evaluator gates | Replay labelled missions and adversarial cases. Invalid/uncertain decisions cannot bypass a deterministic gate or choose an unavailable tool. Compare results against today's routing before activation. |
| 4 | A recovery supervisor that can finish interrupted work. Checkpoints, bounded retries, worker leases, cancellation propagation and resource limits keep a mission moving without repeated user intervention. | Autonomy watchdog, session lifecycle, existing cancellation/process-group fixes and persisted blocked/interrupted states | Inject process crashes, provider timeout, lost connection and quota exhaustion. Recover automatically where allowed; otherwise retain a resumable blocked state and exact next action. No orphan workers or duplicate shipping. |
| 5 | One evidence and exception view across the ecosystem. Show what actually ran, current blockers, configured limits and the next automatic action; collect owner decisions only where required. | Mission Control live aggregator, health/status APIs, revision receipts and delivery evidence | Each displayed success traces to a current receipt and revision. Stale, missing or configuration-only data cannot become green. The operator can diagnose a mission from this one view. |

These priorities extend existing systems rather than add another orchestrator. JEV's immediate contribution is the narrow-decision and progressive-disclosure design; an actual metered JEV adapter is deferred under the existing billing constraint.

## First-five work takes precedence

The continuation audit found that the earlier passing tests did not cover the real Build-form endpoint, default model routing, SDK transport admission or all readiness indicators. Those faults are repaired in the original five local implementation lanes. The final Windows suite retains baseline failures; production activation remains unverified. See `mission-control-readiness-continuation.md` for ownership and failure cases, and the updated verification report for final evidence.
