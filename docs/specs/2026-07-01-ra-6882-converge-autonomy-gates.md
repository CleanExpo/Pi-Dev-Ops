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

**Recommendation:** classify these local-destructive signatures as a distinct tier signal `DESTRUCTIVE_LOCAL` that the **SDK adapter denies** (unattended → no undo path acceptable) but the **CLI adapter maps to L1 pass-through** (human present → normal permission prompt handles it). This preserves *both* current behaviors exactly while unifying the *pattern definitions* — the registry is shared, the disposition differs by adapter, and the difference is documented, not accidental. **This is the single item that changes a live safety control's behavior envelope; it is the Board-level call in this spec.** The recommended option changes *nothing* observable today (both gates keep their current allow/deny on every input) while removing the drift — so it is the safe default and needs only a nod, not a debate. Escalate only if the Board wants the stricter "block rm -rf interactively too" variant.

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
