Moved from SKILL.md. Read when choosing a sandbox provider or an agent provider for a run.

## Selection rules — sandbox provider

| Environment | Default | Why |
|---|---|---|
| Local Mac workstation | `docker` | Fast iteration; Docker Desktop available |
| Railway production (Pi-CEO host) | `vercel` (Firecracker microVM) | No Docker daemon on Railway; Vercel sandbox provider runs Firecracker microVMs |
| CI / GitHub Actions | `noSandbox` (interactive only) | No need for nested isolation; CI is already a sandbox |
| Smoke tests / dry-run | `noSandbox` | Fast, deterministic, no Docker pull |

`podman` is a manual override for hosts without Docker (rootless, drop-in). `daytona` is for users with a Daytona account. `noSandbox` is **never used in autonomy paths** — only smoke tests + interactive sessions.

## Selection rules — agent provider

| Use case | Default | Reason |
|---|---|---|
| Plan / decompose / Margot research | `claudeCode` (sonnet 4.6) | Best at structured JSON output + cited reasoning |
| Implementer (parallel) | `claudeCode` (sonnet 4.6) | Pi-Dev-Ops model-routing policy: planner+orchestrator only opus; everything else sonnet |
| Reviewer | `codex` | Different model for adversarial review (not the same model that wrote the code) |
| Merger | `claudeCode` (opus 4.7) | Merge conflicts need the strongest model; merger is a "Senior Orchestrator" role per RA-1099 |
| Research | `pi` | When the work is research, not code |

Override per-job via `agent` field; defaults are conservative.
