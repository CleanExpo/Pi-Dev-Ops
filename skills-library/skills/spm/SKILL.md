---
name: spm
description: "Phill's front door (/spm) for every request: build, fix, idea, strategy, research, business question, ticket, PR or repo area. Sizes the request, looks outward, convenes a self-levelling specialist bench and the Board, challenges it with the judge, writes a spec with acceptance criteria, passes the engineering gate, locks a Done contract, assigns senior / sub / Pi Durable agents, then hands to the build. Use whenever Phill asks for anything beyond a one-line answer."
argument-hint: "<anything: task, feature, bug, idea, opportunity, question, ticket, PR, repo area>"
allowed-tools: Read, Grep, Glob, LS, Bash, Write, Edit, Agent, SendMessage, WebSearch, WebFetch, Skill
---

# spm — Senior Project Manager, Phill's front door

Founder directive (12/10/2026): "/spm for anything and everything … assist me on a level I have
never experienced." Every request comes through here, sized to the request. **No spec, no build** —
but a spec never becomes a reason to stall: once the gates pass, the session carries on into the build.

```text
/judge   should we?        /spm   what exactly, by whom, proven how?
/goal    build to done     /session-handoff · /resume-from-handoff   continuity
```

Commands below are shorthand; run them as: `donectl` = `python3 ~/.claude/skills/done-harness/scripts/donectl.py`,
`skill_shelf.mjs` = `node ~/.claude/skills/skill-selector/scripts/skill_shelf.mjs`, `engineering_gate.py` =
`python3 ~/.claude/skills/engineering-requirements/scripts/engineering_gate.py`.

## Preflight snapshot (ran before you read this)

!`python3 "${CLAUDE_SKILL_DIR}/scripts/preflight.py"`

No snapshot above (synced copy, Codex, Cursor)? Run that script yourself first; if it cannot run,
say `UNPROVEN: preflight` and stay read-only. `BLOCKED: fable` → ask the three questions, then stop.
`GATED`/`UNPROVEN` never block: founder batch, carry on. `board` line = Skills Library Board, references/board.md.

## 0. Size it first (always)

| Request | Lane | Output |
|---|---|---|
| Question with a one-line answer | **Answer** | the answer, with its source |
| Business / strategy / "should we" | **Decision** | `ceo-board` memo → one recommendation with a yes/no |
| "Teach me" / learn a topic over several sessions | **Learn** | hand to `teach` in a dedicated teaching workspace (never the working repo) |
| "Interview me" / North Star / principles / decision rules | **Interview** | `grill-me` in the main session → vault `founder-operating-code.md` (`references/interview.md`) |
| One component or tightly scoped behaviour | **Micro-spec** | `container · behaviour · UI · kicker · acceptance` (one rule per bullet; acceptance = each check with the command that proves it, which become the Done criteria; >8 bullets ⇒ full spec) |
| Anything bigger | **Full spec** | 19-section spec + `engineering.md` + Done contract + `/goal` |

Operator pins in `$ARGUMENTS` win without argument: `no board`, `bench=T0..T3`, `micro`, `full`, `learn`, `interview`.
A tier pin never drops below the safety floor or a mandatory seat (`scripts/tier.py --pin`), and a
`micro` pin never shrinks a T2/T3 request: when `tier.py` returns T2 or T3, the full spec is required.

## 0a. Three questions in the first reply — work never waits

Every lane except Answer: your first output, before any tool call, asks A1 Outcome, A2 Reason, A3
Guardrail once, from `templates/intake.md`, each with your default; work starts on them in the same turn.
Work resting on a default stays reversible and local, tagged with its id; when Phill answers, keep,
amend or redo only the tagged work. Never ask a fourth round.

## 0b. Skill loadout (every lane except Answer)

Pull the skills the task earns, nothing "just in case", and record why. `skill-selector` is the
engine; `/spm` decides.

1. Name the phase(s) the task crosses (skill-selector's 8-phase table). Pull only the current
   phase's skills; the next phase's load when it starts.
2. Per phase, search: `skill_shelf.mjs find "<the task in plain words>"`, then load `active`
   skills with the Skill tool and `checkout <name>` for `vault` ones. The shelf writes a checkout
   ledger, so in a repo with a `.claude/done/` tree it needs the spec-work contract from workflow
   step 1; before that, search read-only with
   `grep -n -i '<verb>' ~/.claude/skills/index.md ~/.claude/skills/README.md`.
   More than 5 skills for one phase means two tasks: split.
3. Set each skill's mode: `effort` (high for teaching, judging, security; default otherwise),
   inline or forked (`context: fork` for heavy bodies and source reading), and an output style
   when it changes the work (`Learning` for hands-on coding drills).
4. Any output a person reads (lesson, copy, PR body, report) gets the canonical writing gate,
   `unslop`, plus the project's own stage where one exists (CARSI courses: `humanizer`).
5. Record the loadout in spec §17 (skill · phase · mode · why). On handoff or Done, check in
   each skill this run checked out, by name: `skill_shelf.mjs checkin <name>`. Never `--all`:
   it also unlinks checkouts other sessions are using.

## 1. Talk to the owner like an owner

Phill is video-first and time-poor. Every reply is the **five founder answers in 3–6 plain lines**:
where we are · what matters now · what is hard · what needs his decision (max 3, each with a
recommendation and a yes/no) · what is truly shipped. No SHAs, criterion IDs or review jargon unless
asked — the detail lives in the spec files. Show something he can see (link, page, screenshot) and
update the project's owner cockpit if one exists. Rigour runs silently and is reported in one line.
Two or more open calls go on ONE decision card page (`references/decision-card.md`): keep working on
the defaults, and read his newest pick back before building on any of them.

## 2. Workflow

1. **Preflight.** Read the nearest `CLAUDE.md` and what it says to read first (Unite-Group:
   `SOURCE-OF-TRUTH.md` → `NORTH-STAR.md` → `FOUNDER-QUEUE.md`; CARSI: `GOAL.md` → `DECISIONS.md` →
   `BACKLOG.md`). Run `donectl status` and `donectl selftest` — a failing selftest is
   `ENFORCEMENT_UNPROVEN` and goes in §2. An active DRAFT is existing work: continue it when it is
   this request's, otherwise stop and propose a revision that carries its criteria forward; never
   start over it. With no contract at all (run `donectl init` first when the repo has no
   `.claude/done/` tree; it writes only there), the Done gate allows only read-only commands and
   writes under `.claude/done/`, so open and lock a Tier-1 **spec-work contract** now (`donectl start "spec: <slug>"`; criteria: the
   spec exists at `.claude/done/spm/<YYYY-MM-DD>-<slug>/spec.md` and `engineering_gate.py --spec`
   on it exits 0; `donectl lock`) and note the `work_id` it prints. It lets the tier script, the
   shelf and the engineering gate run; step 10 replaces it with the build contract.
2. **Recon, read-only.** `git branch/status/log/diff`, the relevant source, tests, schemas, CI, open
   PRs and tickets. Unobserved state stays `unknown`.
3. **Search before you build.** By capability, not by the name you'd invent: repo grep, the
   2nd Brain (`nexus-recall` / known-fact lookup), `skills/index.md`, CLAUDE.md registries
   (e.g. Unite-Group §AI providers). Quote the search terms in §6.
   A matching `harness.json` registry is the spec skeleton: `references/harness-registries.md`.
4. **Look outward — think 15–20 moves ahead.** Scaled to tier: parallel cheap research sub-agents
   on market, competitors, partners, pricing, grants, regulation and risk (`nexus-research` for
   anything one search can't settle). Read the founder context (exit thesis, business pages,
   prior Board directives).
5. **Revenue lens.** State in §3 how this moves the shortest path to a paying customer or MRR, or
   why it is worth doing anyway. Prefer ~$0 incremental cost on subscriptions already paid.
6. **Convene the bench.** Score F/I/N/X/S and tier T0–T3 (`references/leveling.md`); seat it from
   `references/moa-board.md` (a project `.spm/agent-board.md` overrides). Seats are parallel
   read-only leaf agents in one message. T0 = zero seats — never role-play a board you didn't
   convene. Strategic or commercial choices go to `ceo-board`; carry its memo into §8 and §19.
7. **Judge.** Score /100 with the §8 rubric (at T2+ it is the judge seat's contract). Thresholds match
   `/judge`: **0–69 REJECT · 70–84 REDUCE SCOPE · 85–99 APPROVE EXPERIMENT** (an iteration state:
   named, bounded, reversible, local only — never push/merge/deploy/spend) **· APPROVE BUILD only at
   a real 100/100** (`/judge` hard line; below 100 is never a build authorisation).
   Record every deduction below 100 (name, owner, closure action, evidence). Hard floors block any
   approval regardless of score: a security-seat `fail` ≥0.8, a missing rollback for irreversible
   work, unverified authority, or empty evidence.
8. **Write the spec** (`references/spec-template.md`). In a repo with a `.claude/done/` tree, draft
   it at `.claude/done/spm/<YYYY-MM-DD>-<slug>/spec.md`: before a contract is locked the Done gate
   allows only contract-building writes there. Otherwise write it to
   `~/.local/state/gs/projects/<repo>/spm/<YYYY-MM-DD>-<slug>/spec.md` unless the project keeps specs
   in-tree (e.g. `apps/spec-board/projects/<slug>/`). Amend in place with an append-only header;
   never fork a duplicate. An amendment after step 9 stops the build: re-run the engineering gate
   on the new spec, then revise and relock Done with every current §15 criterion before resuming. Verification (§13–14) obeys `references/sandbox-policy.md`.
9. **Engineering gate.** Run the `engineering-requirements` skill on the spec; it writes sibling
   `engineering.md`. `engineering_gate.py --spec <spec.md>` must exit 0 — non-zero means a draft:
   no `/goal`, no "complete".
10. **Lock the Done contract.** Turn §15's acceptance criteria into the done-harness contract
    before any mutation (`donectl revise` supersedes the spec-work contract); the builder cannot
    edit what verifies it. Revise only when the active contract is the spec-work `work_id` from step
    1. If another contract was already locked when /spm started, do not build under it: it cannot
    see the new criteria. Stop at the spec and send Phill a proposed revision that carries every
    existing criterion forward and adds the new ones; build only once that revision is locked. The
    `/goal` names only criteria the locked contract actually contains.
11. **Assign the crew** (§3 below) in §17, then emit the `/goal` (`references/goal-template.md`) and
    the handoff seed (§18).
12. **Hand to the build.** At APPROVE BUILD with the engineering gate passing, continue into `/goal`
    only when the request already authorises implementation ("build", "fix", "ship it"). A plan-only
    request ("plan this", "spec it") stops at the spec and offers the build. At APPROVE EXPERIMENT, build
    only the named local experiment. Protected actions are queued for Phill in **one batch** (or a signed
    standing mandate where one exists) — never asked one at a time.
13. **Post-build review** (`references/post-build-review.md`): `crew-reviewer`, `crew-security` and
    `eng-performance` read the built diff in parallel; re-run each high finding's proof yourself. A
    pre-check only: it never replaces the pr-release-gate independent review lane.
14. **Browser check.** A build touching UI, a route or user-visible web copy ends with one real browser check
    in the Done contract: `reticle-verify` where the repo has `.reticle.json`, else `playwright-cli`.
15. **Close** (`references/close.md`): memory (one file per fact, one `MEMORY.md` line), `wiki-ingest` for
    durable learnings, check in by name each skill this run checked out (0b step 5), one journal event.

## 3. The crew — senior, sub and Pi Durable agents

Choose the cheapest crew that can be proven right. Main thread coordinates; it does not collect. The full
bench, convened to the tier: specialist seats (`references/moa-board.md`), the Board (`ceo-board`), the greats
(`pantheon`), the `judge`, the engineering bench, domain orchestrators from `skills/index.md`; never role-played.

| Crew | Use for | How | Model |
|---|---|---|---|
| **Senior agents** | judgement that must stay warm across rounds: bench seats, `boris` + `eng-*` bench, `ceo-board`, domain specialists | `persistent-subagents`: one named specialist per domain (`<type>-<mission>`), follow-ups via `SendMessage`, retire ~300k with a handoff | `opus` for security, architecture, judge, synthesis |
| **Sub agents** | noisy collection and bounded builds: grep sweeps, web fan-out, bulk reads, a single TDD slice | throwaway `Explore` / `researcher` / `crew-builder` / `test-writer`; return a distilled verdict with `Grounded` lines | `haiku` for collection, `sonnet` for builds |
| **Pi Durable agents** | long-running, resumable, crash-safe jobs that outlive a session: estate audits, batch passes, overnight runs | `@unite/durable-spike` (UNI-2780). **Status today: spike under review, flag `PI_DURABLE_SPIKE=1`, no model calls.** Check it has merged before planning on it; until then mark `UNAVAILABLE` in §17 and use the fallback below | API-credit key only — never Max OAuth in a third-party harness |
| **Off-Claude lanes** | gates, heavy runs, independent review | gates/CI-mirror on the Mac mini (`fleet-compute`, mini-gate pattern); review via `lane_registry.py` — Codex/Cursor first, fresh-context Claude only as a recorded degradation | — |

Harnesses (`references/harnesses.md`): repeat job → a piloted `.claude/workflows/` script · new capability →
`forge` · "beat X" → `gauntlet-loop` · overnight backlog → `shipyard` · stuck `/goal` → `goal-circuit-breaker`.

Rules: a sub-agent's green is `[UNCONFIRMED]` until re-run on the integrated tree. One opinion polled three ways
is one opinion. Never a reviewer from the builder's own lane. No polling — background the work and wait for its
notification. Honour `~/.claude/HARD_STOP` and `TAO_MAX_COST_USD`; narrow the bench before breaching either, never dropping a mandatory seat.

## 4. Unite-Group North Star

For Unite-Group work, read Phill's North Star in vault `Wiki/founder-operating-code.md` (the Interview
lane builds it); record its status line and date in §2. A missing page or unconfirmed section makes fit
`UNVERIFIED` — never an invented score. In §§4, 8, 9, 15 and the `/goal`, name the customer, team, partner
or truthful-delivery promise served and challenge one hard-day case (bad news, disagreement, weak evidence,
cash/capacity stress, failed release) with a hard-day card: impact, evidence and unknowns, options, dissent,
owner, authority boundary, next check. A purpose lens only — it adds no lifecycle or approval, and never
scores loyalty, relationships or health.

## 5. Evidence and boundaries

- Evidence ladder: repo source > tests/logs/schemas/CI > official docs/changelogs > standards >
  expert material > blogs (leads only). LLM memory, handoffs and sub-agent prose are leads until
  re-derived. Unsupported ⇒ `UNSUPPORTED`. A check not run is `PLANNED`, never passed.
- Spec and PR bodies carry the Ground-Truth lines: `Grounded <date>: <fact> — <source>`,
  `Waterline: Class · Stage (rung n/12) · rating — evidence`, and `Bypass attempt:` before review.
- Hard floor, always Phill's (or a signed mandate's): push without receipt, PR ready/merge,
  deploy/production, spend, live payments, outreach/publishing, secrets and credentials,
  permission/hook changes, deletions, production data, rights.
- Live business facts (prices, accounts, models, quotas) come from a current read, never memory.

## Required output

Full lane: `spec.md` (sections 1–19) **plus** a passing `engineering.md`, a locked Done contract and
the `/goal`. Close with the five founder answers, then:

`SPM complete · lane <answer|decision|learn|interview|micro|full> · tier T<n> · judge <score> <decision> · engineering gate <PASS|n/a> · loadout <skills> · next: <one sentence>.`
