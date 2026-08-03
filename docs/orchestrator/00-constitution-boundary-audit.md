# Constitution boundary audit — every boundary that is not unambiguous or not hard-stop

**Audited:** 2026-08-01 · **Corpus:** `D:\Authority-Site\docs\constitution\` — 14 files, 10,859 lines
**Question asked:** which boundaries can a machine enforce today, without a human interpreting a word?
**Machine audited against:** phill-desktop (this box), live `~/.claude/settings.json`

---

## Verdict

**Not one boundary in the constitution is currently both unambiguous and hard-stop.**

The corpus is not vague — it is unusually well-reasoned prose, and it diagnoses several of its own
defects before I got to them. But it was written to be *read by a person*, and every boundary in it
resolves through a word only a person can weigh (`material`, `significant`, `proportionate`,
`appropriate`). None resolves to a number, an enum, or a path.

That is survivable. What is not survivable is Finding 0.

---

## Finding 0 — the fence is not armed on this machine, and the one gate that could arm it is wired open

This outranks everything else in this document. Verified live, not inferred:

| Control | State on phill-desktop | Evidence |
|---|---|---|
| `PermissionRequest` hook | **Unconditionally returns `{"behavior":"allow"}`** | `~/.claude/settings.json` — a bare `echo` of a static allow decision. No classifier, no matcher, no condition. |
| `PreToolUse` hook | **Not registered.** Events present: SessionStart, Notification, PermissionRequest, Stop, UserPromptSubmit, PostToolUse | same file, `hooks` keys |
| `permissions.allow` | `Bash(*)`, `Write(*)`, `Edit(*)`, `Agent(*)` … wildcards | same file |
| `defaultMode` | `auto` | same file |
| `~/.claude/HARD_STOP` | **Absent** (positive control: `ls` in that dir succeeds) | filesystem |

**Consequence.** Every boundary below is honour-system today. An agent on this box does not *decline*
to spend money or touch production — it is simply *choosing* not to, one turn at a time. `autonomy-ladder`
already predicted this exact failure and named the fix: *"before ANY multi-move executor ships, the L3
gate must live at the SDK permission / hook layer … not only at policy.py's stamp."* That requirement is
**unmet**, and the gate that exists is inverted — it does not merely fail to block, it actively approves.

This is also a direct, live violation of two locked clauses: Ch2 §3 *"may propose — but never
self-approve"*, and Ch6 §6.43's named failure mode *"agent self-authorisation"*. The estate wrote the
prohibition four times from four directions and then wired the machine to do it.

> **The orchestrator's constitution gate therefore cannot be a prompt instruction.** A prompt instruction
> is precisely the control that is currently failing. It must be a `PreToolUse` hook, or it is decoration.

---

## Finding 1 — `material` is the universal solvent

**308 occurrences across the corpus. Zero definitions.** (Positive control: the same grep returns 0 for
dollar figures and non-zero here, so the search works.)

`material` is the qualifier carrying almost every boundary that matters:

- §6.7 human judgement required for *"substantial financial commitments"*, *"significant reputational exposure"*
- §6.15 *"a **material** commitment occurs when Nexus becomes bound…"*
- §6.12 authority revoked when *"context compression causes **material** misunderstanding"*
- §6.26 escalate where *"a stakeholder may be **materially** harmed"*
- §6.33 *"a human instruction does not become constitutional merely because it comes from a human"* — but the trigger to refuse is again materiality

Every one of these is a genuine boundary and none is machine-decidable. An agent asked *"is this
commitment material?"* will answer from its own judgement — which is the self-assessment Ch2 §3 forbids.
**A grader under the control of the graded optimises itself.**

## Finding 2 — zero numeric thresholds, and the only real number lives *below* the constitution

**No dollar figure appears anywhere in 10,859 lines.** Positive control passed: the regex matches
`$500 AUD` in a synthetic file, so the null is real, not a broken query.

Meanwhile `Pi-Dev-Ops/skills/autonomy-ladder/SKILL.md` carries a hard, checkable number: **`spend > $1k` → L3 → STOP.**

That inverts the authority hierarchy the Foundation defines. The only spending boundary in the estate
that a machine can evaluate lives in a *skill* — the bottom layer — while the constitution that claims to
govern it names no figure. This is the estate's own dominant failure mode, already named in Ch2 §8.1:
*"a constraint that binds one system from inside another."* There it was Linear; here it is a skill file.

§6.16 makes it worse by construction: *"A spending delegation **should** include: maximum per
transaction; cumulative period limit…"* — the clause that would produce the number is advisory, and the
number was never produced.

## Finding 3 — `production` is undefined and carries five incompatible senses

25 occurrences, no definition. In use it means at least:

| Sense | Site |
|---|---|
| the deployed environment | EPIC-000 §257 *"installed into the Nexus production environment"* |
| the act of deploying | Ch6 §6.32 *"development from production deployment"* |
| a maturity grade | EPIC-000 *"production-grade"*, *"production-ready"* |
| live customer data | Ch12 §2252 *"use production data beyond permission"* |
| **manufacturing / output** — unrelated | Ch12 §32 *"completion … confused with production activity"*; Ch3 §360 *"the production of an answer"* |

The user's second hard stop is "touching production." A gate keyed on the word `production` as the
constitution uses it would fire on an essay about answer-production and stay silent on a `vercel --prod`.
**The stop needs a path/host/branch allowlist, not a noun.**

## Finding 4 — the boundary-setting clauses are themselves advisory

274 `should` against 632 `MUST`. That ratio is fine in general prose; the problem is *which* clauses got
`should`. The standards that would generate every downstream boundary are advisory:

- §6.5 *"A valid delegation **should** identify: … permitted actions; prohibited actions; spending or resource threshold…"* — the definition of a valid delegation is optional
- §6.16 *"A spending delegation **should** include…"* — see Finding 2
- §6.27 *"A pause **should**: be proportionate; preserve evidence; … define conditions for resumption"*
- §6.35 *"The record **should** include: authority identifier; actor; …"* — the audit schema is optional

A boundary whose *specification* is optional cannot be a hard stop. It is a recommendation about how to
write a recommendation.

## Finding 5 — the hard stops that ARE unambiguous have no mechanism

These are the clauses written as absolutes. They are unambiguous. They are also unenforced — and the
constitution says so itself, which is to its credit:

| Absolute clause | Mechanism | State |
|---|---|---|
| §6.44 *"Nexus must remain capable of stopping what it has made capable of acting."* | `~/.claude/HARD_STOP` | **Absent here.** Ch2 §7: *"the gate has never fired."* |
| §6.27 right of constitutional pause | — | Ch6 annex: *"CANNOT RUN. §6.27's pause has no mechanism."* |
| Level 1 Guardian, emergency suspension | — | Ch2 §9: *"Governance review register — does not exist"*; annex: *"the Guardian does not exist."* |
| §6.6 *"no agent may … declare itself a constitutional authority"* | autonomy check | Ch6 annex: *"zero application call sites."* |
| Ch2 §9 *"every decision is discoverable"* | `cc_decisions` | **0 rows**, and the schema rejects 3 of 5 dispositions |

**An absolute with no mechanism is the most dangerous kind of boundary**, because it reads as protection
in every review and provides none at runtime.

## Finding 6 — the fence's own chapter is not ratified

Chapter 6 — the chapter that defines authority, delegation and agent autonomy, i.e. *the entire fence* —
is marked **"DRAFTED for constitutional validation — not locked."** Its own validation annex scores
**1 of 16 gates run, 0 passed**, and records two structural breaks:

- **4a** — §6.9 defines 8 autonomy levels (0–7); the live schema enforces `CHECK (… BETWEEN 0 AND 5)`. Levels 6 and 7 raise a constraint violation.
- **4b** — §6.10 requires per-domain autonomy (agent × domain × level); `cc_agents.autonomy_max_level` is **a single INT column**. Structurally unimplementable without a new table.

Building an orchestrator that gates on Chapter 6 means gating on an unratified document that contradicts
the database underneath it.

---

## Boundary register

Every boundary relevant to the orchestrator's fence. **U** = unambiguous (machine-decidable without
judgement). **HS** = hard-stop (fails closed, terminal).

| # | Boundary | Source | U | HS | Verdict |
|---|---|---|---|---|---|
| 1 | Spend above a threshold → stop | §6.16 | ✗ | ✗ | No figure exists. Only `$1k` in autonomy-ladder, a lower layer. **Ruling needed.** |
| 2 | No transaction-splitting to dodge thresholds | §6.16 | ✓ | ✗ | Unambiguous *if* a threshold exists (it doesn't). No detector. |
| 3 | Touching production → stop | §6.32 | ✗ | ✗ | `production` undefined, 5 senses. Needs allowlist. |
| 4 | Irreversible action → stop | §6.13 | ✗ | ✗ | 4-way scale resolved by judgement. `policy.py` implements it — but classification is caller-supplied. |
| 5 | No self-expansion of authority | §6.2, §6.42 | ✓ | ✗ | Cleanly unambiguous. **Zero enforcement**, and the live PermissionRequest hook does exactly this. |
| 6 | Silence ≠ approval | §6.25 | ✓ | ✗ | Unambiguous. No mechanism; nothing measures elapsed-silence. |
| 7 | Capability/access ≠ authority | §6.2, §6.20 | ✓ | ✗ | Unambiguous as a rule. Contradicted in practice by `Bash(*)` + auto-allow. |
| 8 | External commitment → verify authority first | §6.15, §6.17 | ✗ | ✗ | Turns on "reasonably interpreted as a commitment". |
| 9 | Material data disclosure → stop | §6.19 | ✗ | ✗ | "Sensitive" undefined; no classifier. |
| 10 | Non-delegable list (16 items) | §6.6 | **✓** | ✗ | **The cleanest boundary in the corpus** — enumerated, closed, no weasel words. Compilable today. |
| 11 | Temporary permission must expire | §6.23 | ✗ | ✗ | "time-bounded **where appropriate**". No expiry field exists. |
| 12 | Emergency powers expire with the emergency | §6.28 | ✗ | ✗ | No emergency state object; nothing to expire. |
| 13 | Agent may not delegate authority it lacks | §6.21 | ✓ | ✗ | Unambiguous. Sub-agent spawn inherits nothing today. |
| 14 | Compression must not convert proposal→approval | §6.40 | ✓ | ✗ | 15 required fields, enumerated. No compressor exists (`context_compressor.py` absent). |
| 15 | Kill switch halts everything | §6.44 | ✓ | ✗ | Unambiguous. **File absent on this machine.** |
| 16 | Denied stays denied | — | — | — | **Not in the constitution at all.** See below. |

**Score: 0 of 16 are both unambiguous and hard-stop. 8 are unambiguous. 0 are hard-stop.**

---

## The gap the brief exposes: "a denied action is terminal" is not in the constitution

The founder's rule — *a denied action stays denied, no reasoning its way back in* — **has no counterpart
anywhere in 10,859 lines.** The closest clauses point the other way:

- §6.24 **Retrospective Ratification** — legitimate emergency action later accepted
- §6.28 **Emergency Authority** — proceed when *"normal approval cannot be obtained in time"*
- §6.29 **Override Authority** — with duration, evidence, restoration

Each is guarded (*"must not be used to normalise unauthorised action"*), but all three are re-entry paths
for an action that was not approved. The constitution assumes denial is a *state to be revisited*. The
brief requires denial to be *terminal*.

**This is a real constitutional gap, not an oversight in the brief.** It needs a new clause, because a
terminal-denial rule that contradicts §6.24/§6.28/§6.29 will lose to them the first time an agent reads
the constitution and finds the escape hatch. Recommend a §6.47 with the narrow carve-out: denial is
terminal for the *agent*; only the founder may re-open, and re-opening creates a new record rather than
reviving the denied one.

---

## What can be compiled into a machine-checkable fence today

Six boundaries survive with no founder ruling required — they are already enumerated and closed:

1. **§6.6 non-delegable list** — 16 enumerated prohibitions → deny-list
2. **§6.21 delegation ceiling** — sub-agent authority ⊆ parent authority → set comparison
3. **§6.40 compression manifest** — 15 required fields → schema validation
4. **§6.42 fingerprint** — 12 lines, already written as assertions
5. **§6.35 log states** — `attempted · authorised · completed · failed · reversed · simulated · proposed` → enum
6. **KILL** — file-exists check, once the file is created

Everything else needs a number, a path list, or a ruling.

---

## Founder rulings required (blocking the fence)

| # | Ruling | Why it blocks |
|---|---|---|
| R1 | **The spend figure.** Per-transaction and cumulative-period. Ratify `$1k` up into the constitution, or set another. | Boundary 1 cannot compile without a number. |
| R2 | **Define "production" as a list** — hosts, branches, projects, DB identifiers. Not a word. | Boundary 3 fires on prose and misses deploys. |
| R3 | **Denied-is-terminal clause**, and its precedence over §6.24/§6.28/§6.29. | Otherwise the rule loses to three locked escape hatches. |
| R4 | **Does "material" get a definition, or does every clause using it get rewritten?** 308 sites. | Half the register turns on this one word. |
| R5 | **Lock Chapter 6, or declare the fence gates a v0.2 subset.** | Currently gating on an unratified chapter that contradicts the schema. |

**Un-blocked and recommended regardless of the rulings:** create `~/.claude/HARD_STOP` handling, register a
`PreToolUse` hook, and remove the unconditional-allow `PermissionRequest` hook. Those three are the
difference between a fence and a description of a fence.

---

*Method: full read of Foundation, Operations and Ch6; targeted greps across all 14 files; live inspection
of this machine's settings. Every null result in this document was positive-controlled before being
reported — one early "settings.json missing" result was a quoting bug in my own check, caught by control
and discarded rather than reported.*
