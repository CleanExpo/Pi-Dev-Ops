# ESTATE LIBRARIAN v1 — brief r4

Revision under three Round-0 cross-vendor BLOCKING verdicts (2026-08-30). This file is
the sole authoritative execution and verification instruction set; anything outside it
is commentary and cannot direct implementation. No unit except W0a runs before a
cross-vendor APPROVE verdict binds to this file's SHA-256 via the review manifest.

## 0. Artifact and bindings

- Artifact: standalone file docs/briefs/estate-librarian-v1.md — UTF-8, LF, no BOM,
  exactly one trailing newline, no embedded copy of its own hash. Its SHA-256,
  repository/base identity and review metadata live in the separate manifest
  docs/briefs/estate-librarian-v1.manifest.json (no self-referential hash).
- Verifier scripts/estate/verify_brief.py: hashes the complete brief file; rejects
  CRLF, BOM, duplicate markers and unexpected trailing bytes; sender and reviewer
  each independently recompute the hash over the bytes they actually hold; the
  review transport binds the payload itself, never a claimed hash string.
- Repository: CleanExpo/Pi-Dev-Ops · remote https://github.com/CleanExpo/Pi-Dev-Ops
- Build branch: claude/estate-librarian-v1-build-sxhfzb
- Base HEAD: 1b47a40f6a59a19f19bb35c2649b03f36f62e4a2 (= origin/main, 2026-08-30)
- Build node: machine_id "ccr-e564c70f" — ephemeral cloud container. Release-state
  ceiling on this node: EPHEMERAL_CANDIDATE_VALIDATED (§8).
- Founder decisions recorded 2026-08-30: D1 standalone-build waiver CANDIDATE (§2) ·
  D2 estate/ namespace (gold = estate/wiki/) · D3 deterministic distiller first ·
  D4 Linear slice (§3). D1 is not effective until hash-bound per §2.

## 1. Hash-bound cross-vendor review (standing)

- Reviewer: different provider family from the author; fresh context; no inherited
  verdict. Anthropic-authored → OpenAI Codex reviews; OpenAI-authored → Claude Max
  reviews. Same-provider review never satisfies independence.
- A verdict binds: brief SHA-256 · provider/model/version · UTC time · exit status ·
  reviewer_response_sha256 · structured verdict (APPROVE | BLOCKING | ADVISORY),
  recorded in the manifest. Any blocking edit changes the hash and voids verdicts.
- Raw reviewer responses: secret/PII-scanned, then encrypted local evidence storage
  only; committed: sanitised verdict, its hash, protected locator.
- No eligible subscription reviewer → REVIEW_UNAVAILABLE and halt. Never silently
  switch to an API lane. The founder is never the transport.

## 1a. Lanes, W0 split, and the deterministic review bridge

- Lane order: deterministic local processing first; subscription lanes next
  (Claude = founder's Claude Max via Claude Code OAuth; Codex = founder's ChatGPT
  subscription via Codex CLI login); OpenRouter or any API only after proven
  subscription unavailability plus a one-use egress approval; PAID use additionally
  requires a money approval. Presence of an OPENROUTER_API_KEY (or any credential)
  never activates a lane by itself.
- Claude lane proof: the effective account is the founder's Claude Max subscription —
  record active login method and plan tier; reject API keys, profiles, federation,
  gateways, Bedrock, Vertex, Foundry and unapproved base-URL/provider overrides;
  prove usage credits and automatic paid continuation are disabled.
- Codex lane proof: founder-controlled machine-level forced_login_method = "chatgpt";
  verify via the app-server account state that the effective account type is ChatGPT
  with the expected plan/workspace; reject API credentials, alternate CODEX_HOME,
  custom providers/base URLs and project-controlled auth overrides; prove paid
  credits cannot be consumed automatically.
- Quota exhaustion returns SUBSCRIPTION_QUOTA_EXHAUSTED with retry_at and halts.
  Never rotate accounts, retry indefinitely, switch providers, consume credits, or
  fall through to an API silently.
- W0a — ephemeral node (this container): install-only compatibility test of the
  pinned plugin and Codex CLI. No founder login, no authentication material, no
  repository, hook, settings or brief modifications. Output: a W0a receipt.
- W0b — founder-controlled durable MacBook or Mac Mini: install the official Codex
  plugin and Codex CLI; the founder performs the one-time ChatGPT login locally;
  authentication files are never copied between machines and never placed on
  ephemeral nodes.
- Pins recorded in the manifest before first review use: official plugin repository
  commit, version and digest; Codex CLI version; Node version; selected
  subscription-supported model; machine identity; credential-store type. Automatic
  upgrades are disabled for this review lane.
- The authoritative review path is the deterministic wrapper
  scripts/estate/review_bridge.sh (runs on the W0b host), not a free-form command.
  It: hands Codex the immutable brief file; requires Codex to independently
  recompute its SHA-256; starts fresh, isolated and read-only; excludes inherited
  verdicts, project MCP servers, hooks and author-controlled reviewer instructions;
  requires strict schema-valid JSON; captures job/thread ID, actual provider/model/
  runtime metadata, exit status and raw-response hash; rejects empty, malformed,
  stalled, truncated or hash-mismatched results; and uses bounded time, bounded
  retries and cancellation.

## 2. Dependency gate (corrected)

- d7751c0a identifies the vendored llm-wiki upstream commit. It is NOT required to
  be an ancestor of Pi-Dev-Ops history.
- The gate scripts/estate/dep_gate.sh binds: canonical llm-wiki upstream repository
  URL and full 40-hex commit; vendoring manifest/path and upstream tree digest; the
  Pi-Dev-Ops integration commit; named U1/U2 acceptance tests. It fetches complete
  canonical histories (git fetch --unshallow on Pi-Dev-Ops; full upstream clone)
  before classifying.
- Honest states: DEPENDENCY_SATISFIED · DEPENDENCY_WAIVED_BY_D1 (requires a
  hash-bound founder decision record plus passing collision/API tests against the
  vendored surface) · BLOCKED_DEPENDENCY (genuinely halts — no unit proceeds).
- Current status: UNVERIFIED. The prior "never existed" conclusion was computed on a
  shallow clone (125 commits) and is void. The shallow window shows no trace;
  full-history verification is the first act of any approved execution. D1 remains a
  waiver candidate only until hash-bound and tested.

## 3. Estates and the source register

- One estate per legal/security boundary, immutable estate_id mapped from stable
  Linear workspace/team/project IDs: est-restoreassist · est-synthex · est-gpilot ·
  est-drnrpg · est-unitegroup. The five teams are NOT blended into one content
  estate; any future merge requires a proven, founder-approved legal and security
  boundary. A portfolio identifier may reference estates but stores no raw sources,
  claims, Gold pages or index rows. No cross-estate join in v1.
- personal-phill: REGISTERED, DISABLED in v1. There is no in-repo imports drop-zone.
- config/estate/source-register.yaml, deny-by-default; per source: source_id,
  estate_id, legal_entity_id, owner/collection_authority, purpose, classification
  (PUBLIC | INTERNAL | INTERNAL-SANITISED | RESTRICTED), inherited acl_policy_id/
  version, retention, permitted_processors, permitted_export_destinations.
- estate_id, legal_entity_id, classification, acl_policy_id/version and complete
  source lineage propagate and are approval-bound through Bronze → claim →
  comparison → proposal → Gold → index → citation.
- Plaintext Git Gold may contain only information authorised for every repository
  and node reader. Narrower-ACL or retention-limited Gold stays in per-estate
  protected storage; Git receives only digests and receipts.
- v1 sources: S1 repo-internal corpus (est-unitegroup; docs/**, brain/**, .spm/**,
  session handoffs, full git history) — INTERNAL, already in-repo. S2a–S2e Linear
  per estate (issues updated within 6 months plus all Urgent/High, with comments;
  manifest records OAuth scope, cursors, watermarks, totals, retries, errors; caps
  loud). S3 Mac Mini transcripts · S4 MacBook transcripts · S5 Obsidian vault:
  UNREACHABLE_FROM_NODE; harvested only when their observation receipts exist — a
  ticket is not a harvest.

## 4. Harvest, quarantine and egress

- Quarantine is out-of-worktree and per-estate (operating-host path outside any git
  repository), operated by a separate least-privilege collector process. Encryption
  is pinned public-key age: collectors hold only the public recipient; private
  identities live in the OS keychain / decryption broker — never in environment
  variables or agent contexts. Quarantine is excluded from git and every remote,
  invisible to the Search Console and to indexing.
- The Linear collector is a non-model process (scripts/estate/collect_linear.py run
  standalone): it streams API pages directly into encryption and returns only
  totals, cursors, errors and opaque receipts. Raw issue/comment bodies never
  appear in Claude or Codex tool transcripts.
- Inventory precedes collection. Observation record (JSONL): source_id, estate_id,
  machine_id, source_hash, collected_hash, byte_count, source_revision_or_mtime,
  observed_at, ingested_at, collector_version, classification, acl_policy_id,
  anchor, result (COLLECTED | PARTIAL | BLOCKED | UNAUTHORISED). No symlink escape
  from allowlisted roots. Unreadable/unauthorised/incomplete → PARTIAL/BLOCKED;
  zero-item results are valid only beside a positive control.
- Secret/credential/PII scanning runs before any logging, inference, staging or
  push. Restricted Silver proposals remain encrypted outside Git; only exact,
  DLP-receipted, INTERNAL-SANITISED outputs may advance.
- Processor/export and retention rules are executable: exact-payload egress
  decisions; approved processor, account, purpose, region and retention; expiry,
  legal hold, purge and no-resurrection controls; deletion receipts covering
  derivatives, caches, logs and indexes.
- Gold admission is not permission to expose content to Claude or Codex. Non-PUBLIC
  agent MCP results require a separate exact-payload export authorisation.
- Distiller harness/estate/distill.py: deterministic extraction is the default and
  first lane (§1a order governs any model lane; free OpenRouter requires the pinned
  model, fallback disabled, $0.00 receipts, and a one-use egress approval). Source
  content is hostile data: it cannot issue instructions, invoke tools, select files
  or cause writes to estate/wiki/**.
- Claims: claim_key, text, status ∈ {SUPPORTED, CONTESTED, UNVERIFIED, SUPERSEDED,
  STALE}, anchors[] (source_id + hash + anchor), confidence. Contradictions become
  comparison files sharing a claim_key, never silently resolved. Approval permits
  admission; it does not make a claim true, current or independently corroborated.

## 5. Gold admission with no self-authorisation

- harness/estate/librarian.py subcommands: propose · import-approval · verify ·
  apply · request-rollback. There is NO approve capability in this repository; the
  repo and its agents never sign an approval.
- External founder-controlled approval mechanism: canonical signed envelope; trust
  root pinned outside this repository; passkey/private signing authority
  unavailable to agents; the envelope binds exact repository, target ref, base
  tree, resulting Gold tree, paths, modes, deletions, proposal hashes, estate,
  policy version and expiry; a durable external nonce ledger advances atomically
  ISSUED → CLAIMED → APPLIED → MERGED → ACTIVATED. Locally created, replayed,
  expired, revoked, wrong-base, wrong-estate or content-mismatched envelopes are
  rejected.
- The authoritative CI verifier (estate-gold-verifier) and branch-protection rules
  are bootstrapped in a separate founder-approved control change BEFORE any gold
  PR. A candidate PR must not introduce or weaken the verifier that approves that
  same PR. Protected rules, an unconditional trusted check and founder-only merge
  are required; agent credentials cannot approve, merge, alter rules or administer
  the approval service.
- Defence-in-depth (non-authoritative): PreToolUse guard denying Write/Edit/
  NotebookEdit into estate/wiki/** outside librarian apply, enforced under
  bypassPermissions; lint_wiki gate in scripts/handoff-loop.sh failing loud on dead
  [[links]], orphans, unapproved pages and gold/index mismatch.

## 6. Retrieval and index activation

- Public HTTP and MCP schemas never accept principal, roles or ACLs as tool
  arguments. The trusted backend derives AuthzContext from the authenticated
  session; wiki_query, wiki_fetch_page and citation resolution share the same
  authoriser and fail closed.
- Result states ANSWERED, INSUFFICIENT, CONFLICTED, STALE, DENIED are all defined
  and tested; approved non-factual conflict metadata is admitted so CONFLICTED is
  actually returnable. Every factual span maps to an approved claim and an
  immutable citation (gold commit + page + anchor). Insufficient evidence →
  abstain. No query-time remote-model or network egress in v1.
- Immutable activation manifest binds: Gold tree/commit; index digest; schema,
  ranker and tokenizer versions; ACL-policy digest; approval and generation IDs.
  Activation is an atomic generation-pointer swap; crash, corruption, concurrent
  query, restart and authorised rollback are tested. Queries fail closed when the
  Gold commit and active index generation differ.
- The tokenizer is pinned; the cap is min(requested_limit, 800) tokens over the
  final serialised HTTP and MCP response, preserving complete claim/citation units.
- Surfaces: MCP server mcp/estate-wiki-server.js registered via .mcp.json; an
  authenticated Mission Control route (app/server/routes/, module ≤300 lines) so
  the Search Console queries through the backend — the browser never calls MCP
  directly. SessionStart hook (appended, composing): query estate-wiki before
  reading transcripts; never paste raw logs where a wiki answer exists.

## 7. Contested-claims fixture

- Isolated fixture estate "fixture-test", never joined to a real estate, excluded
  from every production index: two independently anchored, mutually exclusive
  claims sharing one claim_key, plus one unsupported claim. Outcome: the pair
  becomes CONTESTED with a comparison file, the loner UNVERIFIED; both are refused
  factual Gold admission and never appear in any production index. No arbitrary-
  falsehood-detection claim is made.

## 8. Executable proof suite and release states

Clean-clone caller-bound red-then-green tests (seventeen):
- P1 direct-write bypass: hook denial plus verifier rejection across Write/Edit,
  Bash, Python, cp/mv, git apply, symlinks, other worktrees.
- P2 approval set: missing, forged, content-changed, replayed, expired, revoked,
  wrong-base, wrong-estate; plus concurrent approval replay and revocation.
- P3 cross-estate isolation: two ENABLED, populated estates with identical claim
  keys, terms and page slugs, plus two ACL groups within one estate; allowed and
  denied access proven across query, ranking, fetch, citation, MCP and Search
  Console with no existence-metadata leakage.
- P4 prompt-injection resistance: hostile source content distills inert; nothing
  executes; no gold write.
- P5 secret quarantine, DLP and Git-exfiltration bypass attempts, zero-cost receipt.
- P6 citation validity and unsupported-question abstention.
- P7 hard output cap via the pinned tokenizer over final HTTP and MCP responses.
- P8 stale-index refusal (gold/generation mismatch fails closed).
- P9 interrupted apply, crash, corruption, restart, verified authorised rollback.
- P10 held-out query answerable only from content ingested during the test.
- P11 real authenticated Mission Control Search Console query — browser-level, no
  mocks, no interception.
- P12 lane guards: API credentials present while subscription lanes are healthy →
  refused; quota exhaustion → SUBSCRIPTION_QUOTA_EXHAUSTED with retry_at, no
  paid/API fallback.
- P13 review-bridge integrity: same-provider review rejected; empty or hung plugin
  result rejected; mutated transport bytes rejected.
- P14 self-modified verifier/workflow detection: a candidate change weakening the
  verifier or workflow is caught and blocked.
- P15 conflict, stale and superseded retrieval states returned correctly.
- P16 XSS, unsafe citation URLs and path traversal rejected.
- P17 actual MCP invocation; fresh SessionStart behaviour; restart, scheduled
  drift, retention expiry and runtime observability.
Receipts bind repository, exact SHA, runtime, command, exit code, CI run and
artifact hashes. Redacted transcripts are supporting evidence only. One safe,
sanitised, founder-approved non-fixture Gold batch must exist before the final
Search Console proof, whose result must be ANSWERED with a clickable immutable
citation.

Release states (one honest choice):
- EPHEMERAL_CANDIDATE_VALIDATED — the ceiling for this cloud container: code and
  proofs P1–P10, P12–P17 validated here; durable-host items pending.
- NODE_PILOT_READY — requires the exact pushed/deployed SHA on a named durable
  Mission Control host, required CI, protected rules, final independent
  implementation review, authenticated browser and MCP evidence (P11), Gold/index
  parity, restart recovery, observability and retained external receipts.
- ESTATE_COMPLETE — every declared machine has live parity and query receipts;
  tickets cannot prove it.

## 9. Execution order and ship

- Pre-APPROVE: W0a only (this node, install-only compatibility receipt). W0b and
  the founder control change (§5 bootstrap) are founder actions on durable
  machines.
- Post-APPROVE order: materialise brief + manifest → dep gate full-history
  verification (§2) → scaffolding (register, quarantine layout, guards, gates) →
  librarian + verifier wiring (after the §5 control change) → harvesters →
  distiller → fixtures → retrieval + console route + MCP + hook → proof suite →
  handoff-loop green from clean state → git remote -v → push to
  claude/estate-librarian-v1-build-sxhfzb → git ls-remote confirm → draft PR
  (merge = Phill). CARSI is never pushed.
- Founder actions: W0b; §5 control change; approval envelopes; ESTATE_RAW
  age-recipient provisioning; optional OPENROUTER key with egress approvals;
  wiki-and-audit-v1 reconciliation inputs (upstream URL + full commit + U1/U2
  definitions) for the §2 gate; durable-host deployment for NODE_PILOT_READY.
- Then the standing order: RA-7376 → RA-7379 remainder → RA-7373 (attended) →
  RA-7252.

## Honesty clause

"15-20 moves ahead" is implemented as compounding approved knowledge,
pre-registered plans, and adversarial review — no literal foresight is claimed. No
claim enters gold without a source anchor a human approved, and approval never
converts a claim's epistemic status into truth.
