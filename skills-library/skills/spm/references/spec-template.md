# SPM Spec — <title>

<!-- header (append-only): created <ISO> by <agent/session> · amended <ISO> <commit> <why> -->

### Contents
1 Task · 2 Context · 3 Problem and value · 4 Outcome · 5 Scope · 6 Existing capability ·
7 Bench receipt · 8 Judge · 9 Solution · 10 UX · 11 Technical · 12 Security · 13 Verification ·
14 Stress · 15 Acceptance criteria · 16 Goal · 17 Sequence and crew · 18 Handoff seed · 19 Recommendation

Sections 1–19 are required for the full lane. Write `UNSUPPORTED` / `unknown` / `PLANNED` rather
than leave a cell empty or imply a check ran. `engineering.md` sits beside this file and must pass
`engineering_gate.py --spec <this file>`.

## 1. Task
| Field | Detail |
|---|---|
| Original request (verbatim) | |
| Interpreted task | |
| Lane · tier | answer / decision / micro / full · T0–T3 (axis scores in §7) |
| Target outcome | |

## 2. Current context
| Field | Detail |
|---|---|
| Repo · branch · HEAD · tree | |
| Done preflight | `donectl status` / `selftest` result (exit codes) |
| North Star source + revision | Unite-Group only; else `n/a` |
| Files, PRs, tickets inspected | |
| Known current behaviour | each with a `Grounded` line |
| Unknowns | |

## 3. Problem and value
| Field | Detail |
|---|---|
| User / customer | |
| Pain and current workaround | |
| Revenue path | how this moves the shortest path to a paying customer or MRR, or why it's worth doing anyway |
| Incremental cost | $ / quota consumed; which already-paid subscription covers it |
| Why now | |

## 4. Desired outcome
User-facing outcome · system outcome · what success looks like (observable) · what must not
happen · promise served and the hard-day case (Unite-Group).

## 5. Scope
In scope · out of scope · explicit non-goals · assumptions (each tagged) · constraints.

## 6. Existing capability
Search terms used: `<terms>`
| Capability | Location / source | Reuse? | Notes |
|---|---|---:|---|

## 7. Specialist bench receipt
`T<n> (F… I… N… X… S…) · seats <list> · rounds <n> · split <x> · overlap <lexical/canonical> · board_version <v> · leveling_version <v>`
| Seat | Verdict | Confidence | must_fix (slugs) |
|---|---|---:|---|
Ceo-board memo (decision lane or commercial choice): one-paragraph summary + link.

## 8. Judge challenge
| Category | Score | Notes |
|---|---:|---|
| First-source evidence | /25 | |
| Clear user / business problem | /20 | |
| Reuse of existing capability | /15 | |
| Security / privacy safety | /15 | |
| UX clarity | /10 | |
| Testability | /10 | |
| Cost / control simplicity | /5 | |
| **Total** | **/100** | |

Decision: 0–69 REJECT · 70–84 REDUCE SCOPE · 85–99 APPROVE EXPERIMENT (iteration only: named, bounded,
reversible, local) · APPROVE BUILD only at a real 100/100 (`/judge` hard line). Hard floors checked: security fail ≥0.8 / rollback for irreversible
work / authority / evidence → each `clear` or `BLOCKS`.
Deductions (every point below 100): name · owner · closure action · evidence required.
Decision card (Unite-Group): impact · evidence & unknowns · options · dissent · owner · authority boundary · next check.

## 9. Proposed solution
User flow · system flow · data flow · permission flow · failure flow · rollback path (tested how).

## 10. UX requirements
Entry point · happy path · empty / loading / error states · recovery · confirmations ·
accessibility · copy. UI work starts from a `mobbin-ui-patterns` reference.

## 11. Technical requirements
Files and APIs likely to change · schema / migration impact (Supabase branch first) · config / env
(canonical names) · hooks / skills / agents impact · backward compatibility · performance ·
observability.

## 12. Security and privacy
Auth · permission boundaries · secrets (never in source or transcript) · PII · prompt-injection
surface · external services · approval gates · audit logging · destructive-action controls.

## 13. Verification plan
Environment · isolation mechanism · prod-impossibility guard · teardown (one line each,
`sandbox-policy.md`). Then exact commands grouped: static · unit · integration · browser/UI
(`reticle-verify` where configured) · smoke · manual. Each marked `PLANNED` until run.

## 14. Loop and stress testing
Normal · edge · malformed · large · empty · duplicate / idempotency · permission failure ·
network / API failure · retry · regression · human checkpoint. Name one `Bypass attempt` per
risk surface.

## 15. Acceptance criteria (become the Done contract)
- [ ] AC-1 <objectively checkable; names the command / artefact that proves it>
Every bench must_fix appears here. Production-only checks are human-gated criteria.

## 16. Goal command
```text
/goal <see goal-template.md>
```

## 17. Implementation sequence and crew
| Phase | Objective | Crew (senior / sub / Pi Durable / mini) · model | Validation command | State |
|---|---|---|---|---|
| 1 | | | | idle |
States: idle / WIP / complete / failed. A failed phase amends this spec and stops the build:
the engineering gate re-runs on the amended spec and the Done contract is revised and relocked
with every current §15 criterion before any phase resumes. The builder never silently continues. Pi Durable rows say `UNAVAILABLE → <fallback>` until UNI-2780 has merged.

## 18. Session-handoff seed
What was planned · key files · expected verification · deferred risks · pickup instruction.

## 19. Recommendation
Stop / research more / build smaller / approve experiment / proceed to build — with the founder
batch (max 3 decisions, each with a recommendation and yes/no).

`Waterline: Class <0-3> · Stage <state> (rung <n>/12 <name>) · <AAA|AA|A|FAIL> — evidence: <receipt>`
