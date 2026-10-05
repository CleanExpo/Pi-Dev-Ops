---
type: skill-index
updated: 2026-09-24
---

# Skills Index — Pure-Doc Router

Always loaded; keep ≤60 lines. Intent → canonical entry point; the entry point dispatches its own sub-skills.

| Intent / trigger phrase | Skill |
|---|---|
| `git push` / `gh pr create\|ready\|merge` / opening or updating any PR | `pr-release-gate` (auto-merge threat, checks, conflicts: `merge-gate`) |
| "quality checks failed" / "PR is unstable" / "green locally red in CI" / before any RestoreAssist push | `ci-quality-parity` |
| "tests pass" / "it's green" / "verified" / "done" / "fixed" / "shipped" — before marking anything passing | `proof-discipline` |
| "add a check" / "write a test for" / "gate this" / "guard against" — before the control exists | `control-design` |
| "already failing" / "pre-existing" / "skipped" — reading a verdict you did not write · "nothing found" / "scanned clean" / "no matches" — what did the check look at | `control-readout` · `control-scope` |
| "add it to the fixture" / "paste the token" / "so it still boots" — anything that names a credential | `credential-custody` |
| "is X ready to ship" / go-live / what's blocking launch · "ship the backlog" / "get X production ready" | `readiness-architect` · `gauntlet-ship` |
| "/shipyard" / "run overnight" / "clear the shelf" / "finish these PRs" | `shipyard` |
| "/spm" / "plan this feature" / plan, build, fix or investigate a project task | `spm` |
| "/wayfinder" / too big for one session, too much fog to spec · "/waterline" / "get this out of my head" | `wayfinder` · `waterline` |
| "/bench" / "engineering requirements" / "what am I missing" — before a spec becomes code | `engineering-requirements` |
| "/judge" / pre-build challenge / devil's advocate before approving a build | `judge` |
| "help me decide" / "Board review" / "go or no-go" · "/pantheon" / "what would the greats say" | `ceo-board` · `pantheon` |
| "security review" / "review this PR" / "pressure-test" / "adversarial review" | `opus-adversary` |
| "grill me" / "stress-test this plan" · "ubiquitous language" / "what's the right term" | `grill-me` · `grill-with-docs` |
| "/senior-harness" / full-system overhaul / false-green evidence · /goal hook repeats "Condition unsatisfied" | `senior-harness` · `goal-circuit-breaker` |
| "/new-feature" / starting any feature, fix or task — worktree off `origin/main` | `new-feature` |
| "/session-handoff" / "hand off this session" / before stopping · "/resume-from-handoff" | `session-handoff` · `resume-from-handoff` |
| "/unslop" / before sending any text a person reads (commit, PR body, doc, reply) | `unslop` |
| "what do we know about" / "have we decided" · "search the web for" / "look up" / "who is" | `nexus-recall` · `nexus-search` |
| "research" / "deep dive" / "competitive landscape" · iterative or watched topic: "/deep-loop" | `nexus-research` · `deep-loop` |
| pasted URL / "read this page" / "scrape" · "enrich this list" / "build me a table of" | `nexus-extract` · `nexus-enrich` |
| any scientific task or library (genomics, rdkit, scanpy, astropy, pymc, literature review) | `nexus-scientific` |
| "make a video" / explainer / promo · styled brand reel · avatar / talking head | `video-director` · `brand-video` · `heygen-director` |
| "viral" / "short-form" / "reel" / "TikTok" · "repurpose this video into posts" | `nexus-viral` · `content-cascade` |
| "campaign" / "GTM" / "positioning" · "write/draft copy" / "post" / any public-facing words | `marketing-orchestrator` · `nexus-copywriter` |
| "SEO" / "keyword research" / "backlinks" · "GEO" / "AI search visibility" · "E-E-A-T" | `seo` · `geo-optimization` · `eeat` |
| "build me a deck / poster / page / prototype" from a short prompt · "AI website" / "GBP to site" | `creative-director` · `ai-website` |
| before any UI build / "Mobbin" · "/impeccable" de-slop a frontend · "SwiftUI" / "Liquid Glass" · foldable | `mobbin-ui-patterns` · `impeccable` · `swiftui-liquid-glass` · `swiftui-iphone-duo` |
| "send invoice" / "stripe link" · "onboard {client}" · "SOW" / "draft scope" | `stripe-milestone-invoice` · `client-portal-provision` · `sow-draft` |
| "deploy" / "CI/CD" / "LaunchAgent" · "scheduled task" / "cron job" · "production is down" | `curator-deployment` · `curator-scheduled-tasks` · `vercel-prod-debug` |
| "use the fleet" / "use both machines" / "split the work" · "/crew" · "resume the agent" | `fleet-compute` · `crew` · `persistent-subagents` |
| "autonomy gate" / "can the agent do X autonomously" · "Browser extension is not connected" | `autonomy-ladder` · `chrome-account-align` |
| "install this repo/skills" / "are we bloating the context" · "write a skill" · "/forge" · "which skills do I need" | `skill-watch` · `skill-authoring-standard` · `forge` · `skill-selector` |
| "/context-cockpit" / "why is this session heavy" · Mac Mini disk full | `context-cockpit` · `mac-mini-external-storage` |
| "ingest wiki" / "update brain" · "/wiki-growth" · "adopt the second brain standard" | `wiki-ingest` · `wiki-growth` · `second-brain-adopt` |
| "QA gate" / "PASS or FAIL" · "/build-tournament" · "/gauntlet-loop" / "loop until it beats X" | `qa-lead` · `build-tournament` · `gauntlet-loop` |
| "morning brief" · "triage my inbox" · "reticle" / "verify the flow" (CARSI) | `daily-intel-brief` · `inbox-triage` · `reticle-verify` |
| "council" / specialists consult each other · "nexus prompt" · "actions vs services" | `specialist-council` · `nexus` · `code-structure` |

"/capture-intent" / intent.md / brain dump with no accepted intent → `capture-intent` (Stage 1, before any CEO review). Upstream gstack install (`gstack-*`) → `adopt-gstack`; which set survives is Board Q14. gstack: "I have an idea" / "is this worth building" → `gs-office-hours`; plan scope → `gs-plan-ceo-review`; architecture → `gs-plan-eng-review`; "make the decisions for me" → `gs-autoplan`; lock edits to one folder → `gs-freeze`. Long unattended runs follow `shipyard/references/autonomous-run-contract.md`.
Diagrams ("draw the architecture" / workflow / sequence / data flow / Mermaid) → `archify`. Browser work (automate / UI review / QA a page) → `browser-routing`; headless scripted automation, test generation or PASS/FAIL QA in coding work → `playwright-cli`. Plaud → `plaud-shared` first.
Retired names: `remotion-orchestrator`, `video-orchestrator` → `video-director` · `codex-adversarial` → `adversarial-review` · `semrush` → `seo` · `remotion-colour-family` → `remotion-designer` · `release-path`, `pr-merge-ci-gate` → `merge-gate` · `council-of-logic` → `judge`.

## The Library

- Full catalog: read `~/.claude/skills/README.md`. Hygiene rules: `~/.claude/skills/CLAUDE.md`.
- "which credential" / "where does the key live": read `~/.claude/skills/library/connections.md`, and **before claiming ANY credential is missing, run `find-cred <service>`** (`~/.claude/bin/find-cred`, sweeps all 7 stores). Exit 2 + `INCOMPLETE` means a store could not be searched: never evidence of absence. `--live` checks keys without printing one.
- `updated:` bumps whenever a router row or the README catalog changes.
