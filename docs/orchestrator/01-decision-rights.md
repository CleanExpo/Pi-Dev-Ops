# Decision rights — the fence

**Rule:** the orchestrator stops for exactly two things — **spending money** and **touching production**.
Everything else inside the fence, it does. A denied action is terminal.

This document is the *specification of a compiled artifact*, not a policy essay. Per
[the boundary audit](./00-constitution-boundary-audit.md), prose fences in this estate have a perfect
record of not being enforced. The deliverable is `fence.json` + a `PreToolUse` classifier.

---

## 1. Do not invent a third ladder

Three authority models already exist in this estate. A fourth would be the fifth naming collision.

| Existing | Shape | Where |
|---|---|---|
| `autonomy-ladder` | L0 advise → L1 reversible → L2 cross-domain → **L3 irreversible/strategic = STOP** | `skills/autonomy-ladder/SKILL.md` |
| `swarm/nexus/policy.py` | reversible/low → **auto** · medium/high → **HITL** · irreversible → **founder-only escalation** | live code |
| Constitution Ch6 §6.9 | Levels 0–7 by autonomy class | unratified; schema enforces 0–5 |

**The two stops are not a new model. They are `autonomy-ladder` L3, made checkable.** Money and production
are the two concrete faces of "irreversible", which is the axis `policy.py` already routes on.

So: **reuse `policy.py` as the decision engine; reuse L3 as the tier; add the missing classifier.** The
gap was never the model — it was that classification is caller-supplied, so an agent that mislabels its own
action as "reversible" is auto-approved. The classifier must sit *in front of* the caller.

## 2. The two stops, as predicates

A boundary that resolves through a word a human must weigh is not a boundary (audit Findings 1–3).
Both stops are therefore defined as **enumerations, not adjectives**.

### STOP 1 — money

Fires on any of:

| Predicate | Rule |
|---|---|
| **Direct spend** | Any command invoking a payment/billing surface: `stripe`, `vercel buy_*`, `*_buy_credits`, `buy_domain`, `buy_pro`, `confirm_billing_purchase`, `confirm_cost`, `buy_addon` |
| **Metered generation** | Any credit-consuming MCP call: Artlist/Higgsfield `generate_*`, `upscale_*`, `dubbing`, `create_voice` |
| **Provisioning** | Creating a paid resource: `supabase create_project`, `create_branch`, DO/Vercel project creation, new cron entry |
| **Subscription** | Anything creating a recurring charge, at any amount — §6.16 *"create subscriptions without authority"* |
| **Threshold** | Cumulative or per-transaction spend above **`fence.spend.max_aud`** — *pending ruling R1* |

**Splitting is a stop, not a workaround.** §6.16 forbids dividing transactions to avoid thresholds; the
classifier sums per rolling window, not per call.

> **R1 blocks the numeric arm only.** The enumerated arms (payment surface, metered generation,
> provisioning, subscription) compile today with no ruling. Ship those; leave `max_aud` null and treat
> *any* unenumerated spend as a stop until the figure lands. Fail closed.

### STOP 2 — production

Never keyed on the word `production` (audit Finding 3 — it fires on prose and misses deploys). Keyed on
**identity**:

| Predicate | Rule |
|---|---|
| **Branch** | write/merge/push targeting `main` / `master` on any estate repo |
| **Host** | request to a host in `fence.prod.hosts` — `carsi.com.au`, `disasterrecovery.com.au`, live Vercel/DO aliases |
| **Deploy verb** | `vercel --prod`, `vercel deploy` to a prod alias, `doctl app create/update`, `railway up`, `fly deploy` |
| **Database** | connection string or MCP project-ref in `fence.prod.databases` — e.g. `udooysjajglluvuxkijp` (RA live), `znyjoyjsvjotlzjppzal` (Synthex prod), DO `defaultdb` (CARSI) |
| **Schema change** | `apply_migration`, `prisma db push`, any DDL against a listed database |
| **Secrets** | write to `.env*`, `vercel env add`, `supabase secrets`, key rotation |
| **Outbound** | any send to a real recipient: Telegram send, Gmail send, publish/post, `tiktok_publish` |

`fence.prod.*` is a **list, maintained as data**. Adding a production surface is a fence edit, and a fence
edit is itself a gated action (§4).

## 3. Inside the fence

Everything not matching a stop predicate. Explicitly and deliberately un-gated:

read · grep · analyse · plan · spec · draft · local edit · local test · **local commit** · feature branch
push · **open a PR** · file/update a Linear ticket · write to the wiki · trim its own cache · rewrite its
own prompts · refactor a skill · spawn a sub-agent within its own authority

This list is the point. The failure mode the audit names in §6.43 is not only self-authorisation — it is
also *"operational paralysis caused by unnecessary approvals"* and *"agents being prevented from useful
preparation."* A fence that stops everything is as broken as one that stops nothing.

**Open-PR-never-merge is the hinge.** It is the largest possible amount of finished work that is still
fully reversible. The orchestrator should push work right up to that line without asking.

## 4. Self-modification is inside the fence, with one exception

The orchestrator may rewrite its own prompts, skills, caches and heuristics freely — that is the inner
loop's whole job. Two carve-outs:

1. **It may not edit `fence.json`, the classifier, or the hook that enforces them.** §6.2: *"no system may
   expand its own permissions."* This is the single self-modification that is a STOP. Mechanically: those
   paths are on the production path-list, so the existing STOP-2 predicate already covers them — no new
   machinery.
2. **Every self-modification is logged** (see [inner loop](./03-inner-loop.md)).

## 5. Denied is terminal

**A denied action is dead. Not deferred, not appealable, not re-scopeable by the agent.**

Per audit Finding "the gap the brief exposes", this rule has **no basis in the current constitution** and
in fact contradicts three locked clauses (§6.24 retrospective ratification, §6.28 emergency authority,
§6.29 override). It needs ruling **R3** to be constitutionally sound. Until then it is implemented as a
*local* rule of this orchestrator, which is permitted — an agent may bind itself more tightly than the
constitution requires; it may not bind itself more loosely.

Implementation:

```
on deny(action):
    write DENIED record  -> denials.jsonl  (action fingerprint, reason, timestamp, requester)
    fingerprint = hash(tool, target, normalised_args)
    thereafter: any action matching fingerprint -> refuse WITHOUT re-evaluation
```

**Refuse without re-evaluation is the operative clause.** The failure mode is not an agent that ignores a
denial — it is an agent that re-reasons about it, finds a genuinely better argument, and proceeds. Quality
of reasoning is not an input. The fingerprint check runs *before* the model sees the request.

Only the founder clears a denial, and clearing it creates a **new** record rather than reviving the old
one — so the paper trail shows "denied, then separately re-authorised", never "denied" silently becoming
"allowed".

## 6. Where it is enforced

| Layer | Role | Status |
|---|---|---|
| **`PreToolUse` hook** | Classifies every tool call → tier. Blocks STOP. Checks denial fingerprints. | **MISSING — build this first** |
| `swarm/nexus/policy.py` | Routes reversibility → auto / HITL / founder-escalation | exists |
| `swarm/kill_switch.py` | `TAO_HARD_STOP` halt | exists |
| `~/.claude/HARD_STOP` | operator kill file | **absent on phill-desktop** |
| `PermissionRequest` hook | currently returns unconditional `allow` | **REMOVE — it is an anti-gate** |

**The `PreToolUse` hook is the whole deliverable.** Everything above it is prompt-level and therefore
advisory; everything below it already works. `autonomy-ladder` named this requirement and it remains the
one engineering task that makes the fence real:

> *"the L3 gate must live at the SDK permission / hook layer … not only at policy.py's stamp."*

Fail-closed: hook errors, missing `fence.json`, or an unclassifiable call all resolve to **STOP**, not
allow. An unparseable fence is a stopped agent, never an open one.

---

## fence.json — shape

```jsonc
{
  "version": 1,
  "spend":  { "max_aud": null,               // pending R1; null => all spend stops
              "surfaces": ["stripe","buy_domain","buy_credits","generate_video", "..."] },
  "prod":   { "branches":  ["main","master"],
              "hosts":     ["carsi.com.au","disasterrecovery.com.au","..."],
              "databases": ["udooysjajglluvuxkijp","znyjoyjsvjotlzjppzal","defaultdb"],
              "paths":     ["**/.env*","**/fence.json","**/hooks/PreToolUse/**"],
              "verbs":     ["vercel --prod","doctl app","apply_migration","prisma db push"] },
  "outbound": ["telegram.send","gmail.send","tiktok_publish","..."],
  "denials_log": ".harness/denials.jsonl",
  "on_error": "STOP"
}
```

Data, not prose. Reviewable in a diff. Editable only through a gated action.

---

*Open dependency: R1 (spend figure) and R3 (denied-is-terminal clause) from the boundary audit. Neither
blocks the build — both arms fail closed until ruled.*
