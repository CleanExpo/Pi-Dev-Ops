# Idea-to-live, second pass (28 Sept 2026)

An independent re-read of the code at `origin/main` 61210371, made in parallel with PR #808 and
without seeing it. It adds findings to [pathway.md](pathway.md) and
[routing-reconciliation.md](routing-reconciliation.md); it replaces nothing in them. Where this pass
and the first pass overlap (runner allocation, partial live proof, definition of done), the first pass's
wording in pathway.md stands. Every row was
verified by opening the cited file at that commit.

Founder decision D0 (RA-7818, 28 Sept 2026) already settles the acceptance question: **Pi-Dev-Ops keeps
human merge; a cross-model audit is review evidence, not acceptance.** The evidence under "Review and
acceptance" below is consistent with that decision.

## New pathway breaks

Lettered H onward so they do not collide with A–G in [pathway.md](pathway.md).

| # | Break | Evidence |
|---|---|---|
| H | **Failed mesh runs strand the ticket In Progress.** `claim_update` returns the Linear issue to unstarted only on `released`; a `failed` claim frees the row but leaves the ticket started, and the self-claim query (backlog/unstarted) never offers it again. RA-7796 hit exactly this on 28 Sept. | `app/server/routes/mesh.py:369-378`; `app/server/mesh_lanes.py:29-34` |
| I | **Nothing ever marks a ticket Done.** No Linear Done transition exists in `app/server` or `mesh`. Poller sessions stop at "In Review"; machine-ship "complete" leaves In Progress with a comment. | `app/server/session_linear.py:343-352`; `app/server/spec_pipeline/execution.py:234` |
| J | **Idea and autonomy state may not survive a redeploy.** `.harness/` is gitignored, the Dockerfile only `mkdir`s it and declares no VOLUME, and `IDEAS.md` is appended inside the container. Unverified: a Railway volume outside the repo would change this. | `.gitignore:220`; `Dockerfile:66` |
| K | **Open question, not yet a break: which Vercel project the post-deploy smoke measures.** It checks `pi-dev-ops.vercel.app`. `DEPLOYMENT.md:18` calls that the canonical frontend and says a second, Git-linked project (`pi-dev-ops-unite-group.vercel.app`) auto-deploys from `main` with the same code. If the canonical alias does not follow `main`, the wait-for-SHA step cannot pass on a normal push. The doc dates from April; confirm against the live alias before acting. | `.github/workflows/smoke_test_e2e.yml:52`; `DEPLOYMENT.md:18,29` |
| L | **The plan lane never hands off to build.** After a plan claim, the ticket stays started; no code swaps `idea:plan` for `mesh:auto`. Same dead end as A, reached from the plan side. | `app/server/routes/mesh.py:430` |

## Review and acceptance: rows the first pass did not have

| Text | Code today | Evidence |
|---|---|---|
| A Codex receipt turns "independent review" from NOT_RUN into a recorded review | **In this repo's code a Codex review can never count as independent:** Codex output is always `model_verified=False` ("cannot pass a release audit"), and `independent_identity` needs `model_verified` on both sides. (The estate release gate in skills-library does accept Codex as reviewer: the two rules disagree.) | `app/server/provider_execution.py:42-51`; `app/server/provider_policy.py:105-117`; `tests/test_subscription_policy.py:148-168` |
| Reviewer config `approval_policy="on-request"` via `~/.codex/config.toml` | Code passes `--ignore-user-config`, `--sandbox read-only`, `approval_policy="never"`; read-only matches, the rest does not | `app/server/provider_execution.py:146-161` |
| Codex reads the packet and the candidate diff | Codex runs in an empty temp dir with no checkout: the diff must be inlined in the prompt | `app/server/provider_execution.py:149-151` |
| In-repo pre-push review is cross-model | The pre-push `adversary` is Opus against a Sonnet generator: not independent by the code's own vendor-and-model rule | `app/server/config_loader.py:118` (generator Sonnet), `:120` (adversary Opus); `app/server/provider_policy.py:117` |
| Agent-side merge | `gh pr merge` / push-to-main are L3 and denied without human/Board approval | `swarm/nexus/autonomy_rules.py:43-45`; `swarm/nexus/autonomy_gate.py:54-61` |

## Vendor re-check notes (second fetch)

- **MiniMax OpenAI-compatible URL:** `https://api.minimax.io/v1` is stated on
  `platform.minimax.io/docs/api-reference/text-openai-api`, not on the Anthropic-API page the
  reference cites. Cite the sibling page.
- **Usage-limit pause** (code.claude.com/docs/en/workflows): also requires v2.1.271+, a reset
  within 24 hours, and at most two waits.
- **"16 concurrent agents by default"**: fewer on machines with fewer CPUs.
- **claudelog.com (third-party):** this fetch found "Claude Code's default Opus model from
  v2.1.280"; the first pass recorded that page as last updated 24 Jul with no Opus 5.5 mention.
  The two fetches disagree, so treat the row as unverified; the first-party model page is the
  authority for the 22 Sept release.
