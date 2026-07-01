# Spec — Converge the two autonomy gates on one classifier (RA-6882)

- **Ticket:** RA-6882 (follow-up to RA-6874 / PR #422). Team RestoreAssist, project Pi-Dev-Ops.
- **Status:** Decision-grade spec, pre-implementation. Live safety control — implementation gated on approval of Decision D3 below.
- **Author:** resumed session, 2026-07-01.

## 1. Problem (verified in source)

Two live-ish safety gates now enforce **two different policies** on two disjoint runtime surfaces:

| Gate | File | Surface | Posture | Active? |
|---|---|---|---|---|
| SDK gate | `app/server/tool_gate.py` (214 L) | Autonomous SDK/tao_loop `can_use_tool` callback (`session_sdk.py:_make_can_use_tool`) | **Allowlist / default-deny** | Behind `TAO_TOOL_GATE`, **OFF by default** |
| CLI gate | `swarm/nexus/autonomy_gate.py` (135 L) | Interactive Claude Code `PreToolUse` hook (`.claude/hooks/autonomy_gate_hook.py`) | **Denylist of genuine L3** (L0–L2 pass through) | **Active** via `.claude/settings.json` |

Both are pure (stdlib-only) modules. Both encode destructive-command signatures. The signatures have **already drifted** — each gate blocks things the other lets through:

- **CLI gate does NOT block `rm -rf`, `mkfs`, `dd of=/dev/…`, `find -delete`, `curl … | sh`, interpreter-delete, `DROP TABLE`.** `classify("Bash", {"command": "rm -rf x"})` returns `TIER_LOCAL` (L1) → passes through. The SDK gate blocks every one of these as irreversible.
- **SDK gate does NOT block (as Bash rules) `git merge`, `gh pr merge`, `git push … main`, `vercel deploy`, `supabase migration up`, `gh secret set`, `vercel env add/rm`, real-`.env` writes, `vercel project add`, `gh repo create`, `gh api … branches … protection`, or the `rotate|charge|payout|transfer` verbs.** The CLI gate lifts all of these to L3.
- **Overlap (duplicated, slightly different regexes → drift surface):** `vercel --prod`, `supabase db push`, `prisma migrate`.

A safety control with two divergent, independently-edited pattern sets is a consistency/maintenance hazard: the next person who adds a pattern to one gate silently leaves the other surface exposed.

## 2. Goal / definition of done

Per the ticket's acceptance criteria:

1. **One canonical classifier** (single source of truth for the autonomy tier of any tool call) with thin per-surface adapters.
2. `tool_gate.decide` and `autonomy_gate.decide` both **delegate to the shared classifier** (or the spec documents explicitly why a difference is intentional).
3. **Unit-test parity:** the same `(tool_name, tool_input)` yields a consistent tier on both paths.
4. **Governance:** decide whether safety-control PRs are exempt from auto-merge (PR #422 auto-merged without human review — the very thing it exists to require).

## 3. Design decisions

### D1 — One classifier, two dispositions (NOT one `decide()`)

**Decision:** Extract a single pure `classify(tool_name, tool_input) -> tier (0–3)` plus a single **destructive-signature registry**, into a new module. Both gates import it. Each gate keeps its own `decide()` adapter that maps the shared tier to its surface's posture:

- **SDK loop (autonomous, unattended):** default-**deny** allowlist. Tool not on allowlist → deny. Bash → deny if tier ≥ L2-with-destructive-signature (tighter, because no human is watching).
- **CLI hook (interactive, human at keyboard):** default-**allow**, deny only tier == L3. L0–L2 pass to the normal permission prompt (a human can approve).

**Rationale:** The two postures are *correct and intentional* — an unattended generator must be default-deny; an interactive human session must not be over-blocked or it becomes unusable. Forcing one `decide()` would break one surface's threat model. The hazard the ticket names is not "two postures", it's "two pattern sets". Converging the *classifier + registry* removes the drift while preserving the two intended dispositions. This is exactly the ticket's own "likely" framing.

### D2 — Module home: `swarm/nexus/autonomy_ladder.py`

**Decision:** New pure module `swarm/nexus/autonomy_ladder.py` holding: the `TIER_*` constants, the destructive/L3 signature registry (segment rules, whole-command rules, MCP-name rules, tool-name rules), and `classify()`.

- `autonomy_gate.py` imports it in-package: `from swarm.nexus.autonomy_ladder import classify, TIER_IRREVERSIBLE, …`.
- `tool_gate.py` imports it cross-package: `from swarm.nexus.autonomy_ladder import …`.

**Rationale:** `app/server → swarm` is an already-established dependency direction (`app_factory.py`, `cron_*.py`, `discovery.py` all import `swarm`). The reverse (`swarm → app.server`) exists only lazily in one daemon. So the classifier living in `swarm/nexus` (the ladder is a nexus/autonomy-ladder-skill domain concept) keeps the dependency arrow pointing the established way. Name mirrors the `autonomy-ladder` skill.

### D3 — Reconcile the signature set (the one real safety call) ⚠️

Unifying the registry forces a per-signature decision on **which surface each signature binds**. Two sub-cases:

- **Union of unambiguous L3 (safe, recommended):** every signature currently in *either* gate that is genuinely irreversible/strategic becomes canonical. Net effect: the **CLI hook gains** `git merge`/`gh pr merge` (already had), and the SDK loop gains the prod-push/secret/env/repo-create signatures it lacked. Both surfaces get stricter on genuine L3. No downside — these are all "stop for a human" actions.
- **`rm -rf` / `mkfs` / `dd` / `find -delete` / `curl|sh` / interpreter-delete / `DROP TABLE` (needs a call):** the SDK loop treats these as **deny-irreversible**; the CLI hook currently treats `rm -rf` as **L1 pass-through**. Binding them to L3 on *both* surfaces would make the **interactive** hook start blocking `rm -rf` on a build dir, `dd`, etc. — routine interactive dev commands. That is a behavioral tightening of a human's own session.

**Verified against the test suites** (`tests/test_tool_gate.py`, `swarm/nexus/__tests__/test_autonomy_gate.py`, 128 tests green at baseline): the two suites only assert each gate's *stricter* direction plus benign passes. **No test asserts the looser direction for any cross-gate-divergent signature** (no "CLI allows `npm publish`", no "SDK allows `git merge`"). This makes a strictly behavior-preserving convergence achievable.

**Recommendation (implement now — behavior-preserving):**
- The shared module owns the **regex signature registry** (one definition per signature) and `classify()` (canonical tier). Both gates import both → "one classifier", tier-parity, and drift eliminated.
- **Disposition is preserved per gate by selecting a named subset of the registry**, not by tightening to the union:
  - *Local-destructive* (`rm -rf`, `mkfs`, `dd`, `find -delete`, `curl|sh`, interpreter-delete, `DROP`/`TRUNCATE`/`DELETE`-no-where): **SDK denies** (unattended → no undo acceptable); **CLI passes to the normal permission prompt** (human present; `rm -rf build/` is routine). Preserves both current behaviors exactly.
  - *Strategic-divergent* (`npm publish`, `terraform`, `kubectl delete`, `gh release`, `prisma migrate reset`, force-push-to-non-main on the SDK side; `git merge`, `gh pr merge`, push-to-main, `gh secret set`, `vercel env add/rm`, real-`.env` write, `vercel project add`, `gh repo create`, branch-protection change on the CLI side): each gate keeps the subset it enforces **today**. The divergence is documented in-code per acceptance-criterion #2 ("document explicitly why the two surfaces intentionally differ").
- **Net: zero observable behavior change** — every one of the 128 existing tests stays green as the equivalence proof; the win is a single source of truth for the patterns and the tier.

**The deferred Board-level variant (do NOT implement without a nod):** tighten *both* gates to the full union of L3 signatures. This would make the **active interactive CLI hook hard-block** `rm -rf`, `npm publish`, `terraform apply`, `dd`, `kubectl delete`, `DROP TABLE` in a human's own session. That is a real UX/safety-envelope change to a live control (and, because no test asserts the looser direction, it would shift live behavior while tests stay green — a silent tightening). It is the single Board-level call in this spec; surface it, do not self-authorize it.

### D4 — Governance: safety-control PRs exempt from auto-merge

**Decision:** Add a `safety-control` label; the merge automation skips auto-merge for any PR carrying it, requiring an explicit human approval. Apply the label to this PR and to `tool_gate`/`autonomy_gate`/hook-touching PRs. Small, separate change to the merge-guard workflow — not blocking on D3.

## 4. Implementation plan (post-approval)

1. `verify:` — snapshot current behavior: run `tests/test_tool_gate.py`, `tests/test_session_sdk_tool_gate.py`, `swarm/nexus/__tests__/test_autonomy_gate.py` green (37 tests) as the regression baseline.
2. Create `swarm/nexus/autonomy_ladder.py`: `TIER_*`, the merged signature registry (D3-recommended tiering), `classify()`. Pure, no I/O. → verify: new `tests/test_autonomy_ladder.py` covers each signature → its tier.
3. Refactor `autonomy_gate.py` to import `classify`/tiers from the ladder; delete its now-duplicated local regex tables; keep its `decide()` (L3-deny + HARD_STOP) adapter. → verify: `test_autonomy_gate.py` unchanged-green.
4. Refactor `tool_gate.py`: keep `ALLOWED_TOOLS` allowlist + `decide()` adapter, but source Bash/MCP destructive signatures from the ladder registry instead of its private `_SEGMENT_RULES`/`_WHOLE_RULES`. → verify: `test_tool_gate.py` + `test_session_sdk_tool_gate.py` unchanged-green.
5. Add `tests/test_gate_parity.py`: a table of representative tool calls asserting **both** `tool_gate` and `autonomy_gate` derive the same tier from the shared `classify()` (dispositions may differ by design; tier must not). → verify: parity test green.
6. D4: add `safety-control` label handling to the merge-guard workflow; label this PR. → verify: workflow lint / dry-run.
7. Full `pytest` on touched paths; open PR on branch `phillmcgurk/ra-6882-converge-the-two-autonomy-gates-on-one-classifier` with the D3/D4 decisions called out for human review (do **not** rely on auto-merge — this is the exemption case).

## 5. Risks / non-goals

- **Non-goal:** collapsing the two postures into one gate. Explicitly rejected (D1) — the allowlist-vs-L3-denylist split is intentional and preserved.
- **Non-goal:** making either gate a sandbox. `tool_gate`'s honest-scope note stands: Bash-permitted means write-then-exec and arbitrary interpreter payloads are not fully closed. Convergence does not change this bound.
- **Risk:** a botched registry refactor could silently *weaken* a live gate. Mitigation: steps 3–4 keep every existing test green as an equivalence proof; step 5 adds parity coverage; the CLI gate is the active one and its test file must not change.
- **Risk:** `TAO_TOOL_GATE` is OFF by default, so the SDK gate is not currently enforcing in prod — convergence is a correctness/maintenance win, not an active-incident fix. Flipping it on is out of scope for RA-6882.
```
