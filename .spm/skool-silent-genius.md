# SPM Spec — Skool "Silent Genius" Engagement Loop (Claude Code Club)

Date: 2026-07-05 · Author: /spm · Status: APPROVE EXPERIMENT (pilot authorized by founder message 2026-07-05)

## 1. Task
Build a repeatable respond-and-assist loop inside skool.com/claudecodeclub under Phill's account (phill-mcgurk-9175): find open questions, answer them genuinely well, accumulate engagement points to climb the level ladder, and quietly build authority. "Silent genius" = consistently useful, never promotional.

## 2. Project context
- Account: paying member ($9/mo, joined 2026-06-28, email phill.m@carsi.com.au lane). Level ~1 (verify on first run — points not exposed in member metadata; read from profile/leaderboard).
- Community: 6.7k members, 1,496 posts, daily flow of beginner questions and "Phase N Mission" result posts.
- We hold the full classroom harvest (`2nd Brain/Sources/Claude-Code-Club/`, 30 courses, ~780K teaching text + 2026-07-05 delta) — we can answer curriculum questions with primary-source accuracy.
- Automation lane: browser-harness CDP into Phill's logged-in Chrome (proven this session: feed, course trees, post bodies all extractable via `__NEXT_DATA__` / `_next/data`).

## 3. Problem
Gated classroom packs sit behind engagement levels (evidence: rank cards + classroom lock labels): L2=5pts Cheat Sheet · L3=20pts Prompt Vault + 15 Profitable Builds · L4=65pts MCP Super Pack · L5=155pts Open Claw + Coaching. Points on Skool = likes received on posts/comments (per the pinned "How the Club Works + How to Level Up" post — VERIFY exact wording on first run). Phill has no engagement footprint; the packs stay locked and his authority in the largest paid Claude Code community is zero.

## 4. Desired outcome
1. Unlock L2 within a week, L3 within ~a month (20 likes), harvesting each unlocked pack into the vault as it opens.
2. Phill's profile becomes a recognized helpful voice (comment history of accurate, generous answers).
3. A documented, repeatable loop (this spec + runbook section) that any future session can execute.

## 5. Scope
IN: reading feed/posts; drafting and posting comment replies in Phill's voice; welcoming intros; tracking points/level per run; harvesting newly unlocked packs; vault Outcome logging.
OUT (no-gos): DMs; posting our own threads (later lane); affiliate/promo/links to our properties (first 30 days minimum); answering questions we can't ground in the harvest or our verified practice; any moderation argument; classroom "mission" posts (Lane B, separate decision); paid unlocks ($1,500 Skills Booster — Board-level spend decision).

## 6. Existing capability (don't rebuild)
browser-harness (feed extraction proven) · CCC harvest corpus (answer source) · vault Outcome discipline · curator-scheduled-tasks (future cron lane) · edge-trigger Telegram alerts.

## 7. Specialist board (condensed)
- PM: value = unlocked packs (content we can't otherwise get) + authority channel. Cheap daily loop, compounding return.
- Architect: keep it stateless per run — feed JSON in, replies out, evidence log in vault. No DB. Skool `_next/data` is the read API; UI automation only for the write (comment).
- UX (voice): replies ≤120 words, plain Aussie-practitioner tone, specific next step, no headers/bullets walls, no "As an AI". One emoji max.
- Security: never paste keys/snippets from our private repos; no member PII harvesting; single-account rule (this is the CARSI-lane email — allowed, it's the account that owns the membership).
- QA: every posted reply must be re-verified present via post JSON + screenshot; log both.
- Devil's advocate: (a) AI-generated replies at volume = ban + public embarrassment risk under Phill's real name; (b) points≠likes assumption could be wrong; (c) "answer everything" temptation produces confidently-wrong advice that burns authority permanently. Mitigations → guardrails below.

## 8. Judge challenge
Score: 88/100. Unprovable today: (1) reply quality actually earns likes (no data), (2) community/mod tolerance for high-cadence helpfulness from a new member, (3) points-mechanics wording. Verdict: **APPROVE EXPERIMENT** — pilot ≤5 replies now (founder explicitly authorized "respond and start"), collect real like/mod data for 72h, re-judge for the scheduled loop. A real 100 APPROVE BUILD is only claimable after the pilot proves the three unknowns.

## 9. Proposed solution (the loop)
Per run: (1) pull feed `__NEXT_DATA__` → posts with comments<8, age<48h; (2) classify: question we can ground / intro / skip; (3) draft reply per voice card, grounded in harvest or verified practice; (4) post via UI, human-paced (≥45s between replies, ≤5/run, ≤1 run/day); (5) verify + screenshot; (6) append to vault Outcome log; (7) read own profile points/level, record delta; (8) on newly reached level: harvest the unlocked pack to Sources/ same run.

## 10. UX / voice card
First-person Phill: restoration-industry owner who builds with Claude daily. Answer the actual question first sentence. One concrete next step. Admit unknowns plainly ("haven't seen it in the classroom yet"). Recommend what serves THE ASKER in Duncan's curriculum — the substitute-our-stack rule governs our internal builds, not advice to members.

## 11. Technical
Read: `/_next/data/<buildId>/claudecodeclub/…` with `__N_REDIRECT` follow (proven). Write: navigate post URL, focus comment editor, CDP `Input.insertText`, click COMMENT, re-fetch to confirm. Serial browser control only (no parallel agents on Chrome).

## 12. Security
No credentials typed; no external links in replies except official Anthropic docs; stop-and-surface on any login/captcha challenge; evidence stays in vault (private repo).

## 13. Verification
Per reply: post JSON contains our comment id + screenshot. Per run: points/level readout. Pilot success = 5 replies live, ≥3 cumulative likes within 72h, 0 mod actions.

## 14. Loop/stress
Failure modes: comment editor DOM change (fall back to screenshot+click_at_xy); rate-limit/captcha (halt, surface); deleted reply (edge-trigger alert, halt lane); like-drought (revise voice card before run 4, don't increase volume).

## 15. Acceptance criteria (experiment)
[ ] ≤5 replies posted, each grounded + verified live · [ ] evidence log in vault Outcomes · [ ] points baseline recorded · [ ] 72h re-check scheduled · [ ] zero guardrail crossings.

## 16. Goal command
`/goal Run one silent-genius pilot batch per spec .spm/skool-silent-genius.md: ≤5 grounded replies on open CCC questions via browser-harness, verify each live, log evidence to vault Outcomes, record points baseline. Stop on any moderation signal.`

## 17. Implementation sequence
Pilot now (this session) → 72h observation → re-judge → if pass: daily cron via curator-scheduled-tasks + weekly voice-card review → pack harvest on each unlock.

## 18. Session-handoff seed
State: spec at Pi-Dev-Ops/.spm/skool-silent-genius.md; harvest at 2nd Brain/Sources/Claude-Code-Club/; browser lane = browser-harness into logged-in Chrome (needs chrome://inspect Allow after Chrome restarts). Next: check pilot replies' likes + mod status, then re-judge §8.

## 19. Final recommendation
Run the pilot now (authorized), keep volume low, let reply quality — not cadence — do the climbing. The unlocked packs are the concrete payoff; the authority channel is the compounding one.
