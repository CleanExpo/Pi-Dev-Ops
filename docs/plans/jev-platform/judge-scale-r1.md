**72/100 — DO NOT APPROVE BUILD.** The plan reopens the disclosure defect resolved by Level 8 and does not hard-cap Gemini spending.

1. **P0/P1 defects**

   - **P1 — Public does not mean permissible to disclose.** A public `notes.md` can contain an accidentally committed credential or copied standards text without naming its publisher. `sensitive()` cannot establish absence of either. Removing positive approval therefore weakens the previously approved boundary. See [PLAN.md:48](/tmp/jev-judge-scale/PLAN.md:48) and [ask.py:31](/tmp/jev-judge-scale/ask.py:31).

   - **P1 — `origin/main` is not proof of public provenance.** It is a mutable local ref: it can be stale, point to a locally created commit, or survive changing `origin` to an unrelated public repository. Checking that repository’s visibility does not authenticate the local tree. Bind the canonical remote identity and remotely verified commit to the exact objects read; disable Git replacement objects. See [PLAN.md:53](/tmp/jev-judge-scale/PLAN.md:53).

   - **P1 — Free-text channels bypass the claimed boundary.** The initial Gemini prompt has no admission rule. Level 10 state relies on regex screening; question criteria/options and standalone `pick_first` inputs lack an explicit complete admission contract. Private information can leave without appearing in any file. Apply admission to the entire outbound payload for both providers, including tool results. See [PLAN.md:66](/tmp/jev-judge-scale/PLAN.md:66), [PLAN.md:83](/tmp/jev-judge-scale/PLAN.md:83), and [PLAN.md:93](/tmp/jev-judge-scale/PLAN.md:93).

   - **P1 — Gemini’s cap is retrospective; the writer has none.** Observed usage arrives after spending. One request can cross $0.05; missing usage and uncertain failures are unspecified. Require conservative reservation **before every attempt**, bounded input/output/thinking, retained reservations after uncertain failures, and a shared run budget covering retries and writer batches. Select valid pricing before sending; later recalculation cannot enforce a cap. See [PLAN.md:112](/tmp/jev-judge-scale/PLAN.md:112) and [PLAN.md:120](/tmp/jev-judge-scale/PLAN.md:120).

   - **P1 — New failure semantics are incomplete.** Specify that failed or malformed `pick_first` responses produce `unavailable`, distinct from a valid `none`/low-confidence result. Gemini outages, blocked responses and interrupted runs must likewise remain unavailable; generated prose cannot substitute for missing Jev evidence. The reference picker provides no such contract. See [PLAN.md:83](/tmp/jev-judge-scale/PLAN.md:83).

   No direct action-clearance mechanism is specified: retaining read-only tools and excluding shell execution is appropriate.

2. **Is the public boundary sound?**

   **No.** Correctly authenticated public provenance still does not satisfy the estate’s prohibition on sending secrets or banned text, and says nothing about agent-written state.

   The smallest safe first version retains Level 8’s **reviewed, exact-content manifest and reviewed templates**, while expanding globs only over admitted files. Explicitly admit initial prompts and state too. Free-form generation needs a separately specified trusted-input boundary; regex screening alone is insufficient. Public visibility can remain an additional check.

3. **Can the writer control fail, and does it protect labels?**

   **It can fail, but it is insufficient.** Agreement below the relative threshold or a missing class yields `do-not-use`. However, Claude at 20% and Gemini at 15% still pass if every class appears. Fifty cases can also conceal severe class or label imbalance.

   Before bulk eligibility, require:

   - A frozen, matched rule/class/label sampling schedule and an absolute agreement floor.
   - Explicit denominators, with malformed cases, unavailable labels and disagreements reported rather than silently excluded.
   - Per-case admission only when the writer and blind Codex label agree.
   - Independently checked anchor cases, including arithmetic/date failures, and an explicit statement that model agreement is proxy evidence, not correctness.

4. **Other mandatory first-version corrections**

   - **Fix the picker limit:** 255 candidates plus `none` creates 256 options. Reserve sentinel slots within the actual choice cap; handle empty lists, duplicates and sentinel-name collisions.
   - Require negative tests and mutants for the disclosure, provenance, reservation and unavailable-result paths above, plus a deliberately failing writer control.
   - Correct the Level 10 size claim: 64,000 serialized bytes is not 60k tokens; twenty individually valid files can exceed the aggregate limit.
   - Four-worker concurrency can be deferred to simplify the first build. Existing `Budget.reserve()` is locked and has a fixed attempt cap; that reuse is supported by the supplied code.

5. **Score**

   | Category | Score |
   |---|---:|
   | Evidence | 20/25 |
   | Problem | 20/20 |
   | Reuse | 13/15 |
   | Security | 4/15 |
   | UX | 7/10 |
   | Testability | 7/10 |
   | Cost | 1/5 |
   | **Total** | **72/100** |

   Approval requires the disclosure/provenance corrections, prepaid budget enforcement, explicit failure contracts, stronger writer control, picker correction and corresponding tests listed above.

Reviewed all ten brief-required files. **Files changed: none.** Checks were static inspection only; no implementation tests or network calls ran. Provider/model/pricing claims remain supplied assertions. Next step: revise the plan against these blockers.