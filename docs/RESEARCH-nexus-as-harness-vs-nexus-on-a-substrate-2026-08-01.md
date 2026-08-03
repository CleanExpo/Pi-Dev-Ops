# Nexus as harness versus Nexus on a substrate

**Date:** 2026-08-01 · **For:** Phill McGurk
**Method:** primary sources only — the `block/buzz` repository and its in-repo docs and NIPs, the Nostr NIP-34 specification, and the Agent Client Protocol repository. No secondary write-ups, no blog posts, no summaries. Where a fetch produced a claim I could not corroborate at the source, I say so inline.

**One correction recorded up front, because it changes a lock-in argument.** A first pass attributed the Agent Client Protocol to Anthropic. That is wrong. ACP is maintained by the `agentclientprotocol` organisation (originating at Zed Industries), Apache-2.0, stable protocol version `1`. The docs site mentions Claude Code only as an implementing agent. I caught this by fetching the repository rather than the docs site.

---

## The question, stated precisely

Nexus today is a **harness**: a set of hand-wired controls that sit around off-the-shelf tools and bolt them together. The alternative is a **substrate**: one signed event log that every actor — human or agent — reads and writes, where the controls are properties of the log rather than scripts around it.

Buzz is the substrate candidate. The question is not "is Buzz good." It is **which layer of our problem does a substrate actually solve, and which does it leave exactly where it was.**

That distinction turns out to be the whole answer, so I will state it before the evidence rather than after:

> **Buzz addresses what an agent may *say*. The fence addresses what an agent may *do*. These are different planes, and no amount of event-log elegance collapses one into the other.**

---

## Part 1 — What Nexus hand-wires today, and what each piece costs

Measured, not estimated: **1,227 lines** across `fence/` (438 classifier, 181 drift check, 145 fence config, 83 notifier, plus tooling), spanning **59 repositories**, **155 skills**, and **11 scheduled workflows**.

| Piece | What it is | What it costs to maintain |
|---|---|---|
| **The fence** (`pretooluse_fence.py` + `fence.json`) | 438-line PreToolUse classifier; 145-line production definition | **Rots by default.** The production list is a snapshot of four external systems. Already proven: the drift check's first live run found `disaster-recovery-redis` missing. Regex maintenance is ongoing and false positives are structural — it flagged a command that merely *contained* the string `vercel deploy --prod`. Worst cost: **it does not propagate.** `settings.json` is gitignored, so the fence exists on exactly one machine and a fresh box inherits nothing. |
| **The denial log** (`denials.jsonl`) | Append-only JSONL of terminal denials, two fingerprints each | **Unsigned, unreplicated, locally mutable.** Anyone with disk access edits it; nothing detects that. It is the record that makes R3 terminal, and it has no integrity guarantee beyond a glob that freezes the agent for touching it. Single machine, no history beyond the file. |
| **The drift check** (`drift_check.py` + workflow) | Re-pulls GitHub, Supabase, Vercel, DigitalOcean; diffs `fence.json` | **Four credentials, four failure modes.** Degrades to `UNCHECKED` per source — correct behaviour, but it means partial answers are the normal case. Currently Supabase is unchecked because the token isn't set. Costs a scheduled runner and four secrets that each expire independently. |
| **Incident notes → Telegram** (`notify.py`) | Outbound-only sender, plain-English incident files | **Inert until a founder-supplied token exists**, and one-way by design. No delivery guarantee, no acknowledgement, no thread. An incident is a file on one disk plus a best-effort push. |
| **Cross-model review** (`opus-adversary`, Codex) | Adversarial second opinion before merge | **Manually invoked, unrecorded.** There is no artefact proving a review happened, no binding to a commit, and no way for a later agent to discover that a decision was already challenged. |
| **Founder-as-message-bus** | Phill relays state between repos, machines, sessions, and agents | **The dominant cost, and the one that does not scale.** 59 repos with no shared log. Every cross-repo handoff, every "did we already decide this", every agent-to-agent result passes through one person. The estate's own constitution names this: momentum was *"100% human-supplied."* |

**The honest summary of Part 1:** five of the six pieces are cheap individually and expensive collectively, because each is a separate file, on one machine, with its own failure mode and no shared identity. The sixth — the founder as the bus — is not a maintenance cost at all. It is a ceiling.

---

## Part 2 — What Buzz collapses, and what is actually built

Buzz is `block/buzz`, **Apache-2.0**, positioned as *"a self-hostable workspace where humans and AI agents share the same rooms."* Architecture: a Rust WebSocket/REST relay (`buzz-relay`) over PostgreSQL (events + search), Redis (pub/sub), and S3/MinIO, implementing NIP-01 (core), NIP-42 (auth), and NIP-34 (git events), with clients including desktop/mobile, a CLI, and LLM agents via an **ACP harness**.

The core claim, from the README:

> *"Every message, reaction, workflow step, review approval, and git event is a signed event in one log. Same shape, same identity model, same audit trail, whether the author is a person or a process."*

And on agents:

> *"Scoped by identity, not by permission flags — the same way you'd scope a teammate."*

That is a genuinely better model than ours for the things it covers. Mapped against Part 1:

| Our piece | What Buzz replaces it with | Real? |
|---|---|---|
| denial log, audit log, shadow log | one signed event log, per-event Schnorr signature, searchable | **Works today** |
| incident notes → Telegram | channel messages + threads in the room the agents are already in | **Works today** (push notifications: *planned*) |
| founder-as-message-bus | agents with own keypairs and channel memberships, posting into shared rooms | **Works today** |
| cross-model review | review approvals as signed events bound to git events | partially — approvals exist as events; **approval gates are *in progress*** |
| the fence | — | **nothing** — see below |
| drift check | — | nothing; drift against external SaaS is our problem, not the substrate's |

### Marked honestly, from the README's own status table

- **Working today:** relay, channels, threads, DMs, canvases, media, search, audit log; desktop app (Tauri + React); `buzz-cli` + ACP harness; YAML workflows (message/reaction/schedule/webhook); git events (NIP-34).
- **In progress:** mobile clients; **workflow approval gates**; huddle lifecycle events.
- **Planned:** web-of-trust reputation; push notifications; culture features.

### The finding that decides this document

I went looking for the mechanism that would let Buzz host our fence. It does not exist. From `docs/MCP_DRIVEN_HOOKS.md`, Buzz implements exactly two lifecycle hooks — `_Stop` (fires *before the agent honors* an `end_turn`) and `_PostCompact` (after context compaction). And the normative statement:

> **"Hooks are advisory, not authoritative."**

For `_Stop`: *"Non-empty text = objection (agent continues). Empty = no objection (agent stops)."* An objection that lets the agent continue is not a gate. There is **no pre-execution hook**, and the document contains **no human sign-off mechanism** at all — the only adjacent feature, `BUZZ_AGENT_REQUIRE_REPLY=1`, *"reminds the model to publish"*.

Compare our fence: `exit 2` on a `PreToolUse` hook, which refuses the tool call before it runs, regardless of what the model wants. Advisory versus authoritative is not a maturity gap that time closes on its own — it is a different design point, at the opposite end of the agent lifecycle.

The two identity NIPs are also less finished than the README implies:

- **NIP-AA (Agent Authentication)** — real and well-specified: owner↔agent keypair binding on `kind:22242`, RFC-2119 throughout, optional per-event `kind=` scoping, *"MUST NOT create a persistent membership record"*, *"virtual members MUST NOT be granted relay administration privileges."* Status: **`draft`, `optional`** — *"relays MAY implement NIP-AA; it is not required."*
- **NIP-AP (Agent Personas)** — `kind:30175`/`30178`. Status **`draft`**, and behavioural fields are *"parsed but not yet applied."* Its access control is *data visibility* filtering, not authorisation.

**So the honest scoreboard:** the message bus, the audit log, and shared-room agent identity are built and usable. The control plane is drafted, optional, or in progress. Adopting Buzz today buys you the first set and buys you nothing for the second.

---

## Part 3 — What breaks if we move

Our stack: **Linear, Supabase, Vercel, GitHub, Obsidian.**

### Does a substrate replace them or sit beside them?

**It sits beside them. All five.** Not one is replaced today, and for three of them the answer is structural rather than a matter of maturity.

| System | Buzz equivalent | Verdict |
|---|---|---|
| **Linear** | NIP-34 `kind:1621` issues + status kinds `1630`–`1633` (open / applied / closed / draft) | **Beside.** The event kinds model an issue's *existence and state*, not cycles, estimates, projects, triage, or the board semantics the estate actually runs on. Our own continuity spine puts the plan on Linear precisely because it survives context loss; four status kinds do not replace that. |
| **Supabase** | Buzz's own PostgreSQL, for *its* events | **Beside.** Buzz's Postgres stores the event log. It is not an application database. RestoreAssist and Synthex talk to their own Supabase projects and always will. |
| **Vercel** | none | **Beside.** Orthogonal. Buzz is not a hosting platform. |
| **GitHub** | NIP-34 kinds `30617` (repo announce), `30618` (repo state), `1617` (patches), `1618`/`1619` (PRs), `1621` (issues) | **Beside, firmly.** NIP-34 announces and mirrors git; **Buzz's own git hosting backend is listed as *planned***. More decisively: the estate's only *working* structural gates are GitHub branch protection and required reviews — the things we turned on this week. NIP-34 has **no analogue for branch protection, required status checks, or required reviewers**, and the spec itself flags unfinished business: *"inline file comments kind … remains unimplemented."* Moving git off GitHub would delete our only real gates to gain a signed mirror. |
| **Obsidian** | canvases, search | **Beside.** The 2nd Brain is a file-backed vault with deterministic recall through `brain.js`. Buzz canvases are a collaboration surface, not a knowledge substrate. |

**What Buzz would actually replace is none of the five. It replaces the glue** — `denials.jsonl`, `fence.jsonl`, `shadow.jsonl`, incident files, the Telegram feed, and the founder-as-bus. That is a smaller claim than "substrate replaces stack," and it is the true one.

### Migration cost

- **Infrastructure you now operate:** a Rust relay, PostgreSQL, Redis, and S3/MinIO — self-hosted. That is a new production dependency for an estate whose scheduled workflows are already failing 4-in-12.
- **Key management:** a keypair per agent, per machine. Today we cannot reliably propagate a gitignored `settings.json`; keypair custody is strictly harder than that, and it is exactly the credential-plane problem the estate has already identified as its blocker.
- **Rewrites:** `notify.py` and the audit emitters become event publishers. Small — perhaps a day. This is the cheap part.
- **The expensive part is none of the above.** It is that a second system of record starts accumulating truth, and for a period both it and Linear are half-right. Our own audit found three governance models live and unreconciled. A fourth substrate, adopted enthusiastically and half-migrated, is that failure repeated with better cryptography.

### Lock-in risk of a young Block project

Lower than instinct suggests, for a specific and checkable reason: **Apache-2.0, self-hostable, and built on an open protocol.** Events are Nostr events. If Block stops work tomorrow, the log remains readable by any Nostr client, the relay is a Rust service you already run, and NIP-01/42/34 are specified outside the project. That is a genuinely cheap exit — cheaper than our current dependence on a single machine's gitignored hook.

The real risk is not licence capture, it is **abandonment before the parts we need are finished.** The features that would make Buzz a control plane rather than a bus — approval gates, git hosting, web-of-trust — are precisely the ones marked *in progress* and *planned*. Betting on a substrate for capabilities it does not yet have is a bet on someone else's roadmap.

I did not find, and therefore do not assert, anything about Block's maintenance track record on this project. Commit cadence and issue responsiveness are checkable and worth checking before Stage 2 below.

---

## Part 4 — Verdict and staged path

### The genuine engineering verdict

**Adopt Buzz as the event log and message bus. Do not adopt it as the control plane. Keep the fence exactly where it is.**

The reasoning, in one line: our two problems are *"nothing stops a bad action"* and *"nothing carries state between agents,"* and Buzz solves the second completely while solving none of the first.

The failure mode I want to name explicitly, because it is seductive: Buzz's pitch — one log, one identity model, signed, auditable — sounds like governance. It is not governance, it is **attestation**. An agent with a Buzz keypair scoped to a channel can still run `vercel deploy --prod` on the laptop, because Buzz never sees the tool call. The relay would faithfully record that the agent *said* it deployed, immutably, with a valid signature. It would not have stopped it. Swapping an authoritative `PreToolUse` block for an advisory `_Stop` objection would be a strict downgrade in the only place we currently have real enforcement.

Equally, refusing Buzz because it isn't a fence would be the opposite error. The founder-as-message-bus is our ceiling, and a signed shared log with identity-scoped agents is a genuinely better answer to it than anything we would hand-roll. We should not build our own event log. That way lies a fourth unreconciled governance model.

**Harness and substrate are not competing answers. The fence is a control plane; Buzz is a bus. Run both, and do not let either pretend to be the other.**

### Staged path — smallest first step that tests the idea without betting the estate

**Stage 0 — One-way mirror. Additive, reversible, zero systems of record moved.**
Stand up one self-hosted relay. One channel. Publish only what the fence *already writes*: `shadow.jsonl` rows, incident notes, drift reports. Nothing reads back; nothing depends on it. Cost: a relay and a publisher. Tests the only question that matters at this stage — *does a signed shared log actually reduce the founder-as-bus load, or does it become a feed nobody reads?*
**Kill criterion:** if nobody reads the channel in three weeks, the substrate thesis is wrong for us and Stage 0 is deleted with no residue.

**Stage 1 — Second identity.** Give one agent its own keypair under NIP-AA and have it post results into the channel instead of returning them to Phill. Tests identity scoping against a real workflow. Still no system of record moved.
**Kill criterion:** key custody proves harder than the propagation problem we already have.

**Stage 2 — Cross-repo handoff.** Move one genuine handoff — say, drift findings from the hub to a spoke — from "Phill relays it" to "both agents are in the room." This is the first stage that delivers the actual prize. Before entering it, check the repository's commit cadence and issue responsiveness.

**Stage 3 — Re-evaluate, gated on someone else's roadmap.** Only when **workflow approval gates ship and leave `in progress`** does the question "could Buzz hold part of the control plane" become answerable. Until then it is not a decision, it is a wish.

**Never:** move Linear, Supabase, Vercel, GitHub, or the vault onto the substrate. They are beside it, permanently, until a specific and separate case is made for each — and for GitHub the case must first explain what replaces branch protection.

---

## Sources

All primary. Fetched 2026-08-01.

- `block/buzz` repository and README — https://github.com/block/buzz · raw README: https://raw.githubusercontent.com/block/buzz/main/README.md
- Buzz in-repo docs index — https://github.com/block/buzz/tree/main/docs
- Buzz `docs/MCP_DRIVEN_HOOKS.md` — https://raw.githubusercontent.com/block/buzz/main/docs/MCP_DRIVEN_HOOKS.md *(source of "Hooks are advisory, not authoritative")*
- Buzz custom NIPs index — https://github.com/block/buzz/tree/main/docs/nips
- Buzz NIP-AA (Agent Authentication) — https://raw.githubusercontent.com/block/buzz/main/docs/nips/NIP-AA.md
- Buzz NIP-AP (Agent Personas) — https://raw.githubusercontent.com/block/buzz/main/docs/nips/NIP-AP.md
- Nostr NIP-34 (git stuff) — https://github.com/nostr-protocol/nips/blob/master/34.md
- Agent Client Protocol repository — https://github.com/zed-industries/agent-client-protocol *(redirects to the `agentclientprotocol` org; Apache-2.0, protocol version `1`)*
- Agent Client Protocol introduction — https://agentclientprotocol.com/overview/introduction

**Known gaps in this research, stated rather than papered over:**
1. The Buzz NIPs index returned filenames without bodies; I read NIP-AA and NIP-AP directly but did **not** read the other thirteen (AE, AM, AO, CW, DV, ER, GS, IA, MP, OA, PL, RS, WP). One of them may bear on approvals; I did not verify either way.
2. I did not inspect commit history or issue responsiveness, so I make no claim about project momentum. That check belongs before Stage 2.
3. Buzz's `docs/formal/` and `docs/spec/` subdirectories were not read.
