---
name: sandcastle-runner
description: The primitive. Wraps a single Sandcastle invocation (`npx sandcastle run`) so Pi-CEO orchestrator can spawn AFK code-executing agents in isolated Docker / Podman / Vercel-Firecracker / Daytona sandboxes. Pluggable agent (Claude Code / Codex / Pi / OpenCode) and pluggable sandbox provider. Stream stdout into session.logs. Pre-flight kill-switch + concurrency cap. Closes Wave 5 #1 (RA-1856 epic).
owner_role: Builder
status: wave-5
---

# sandcastle-runner

The Pi-CEO ↔ Sandcastle bridge. One subprocess boundary. Every other Wave 5 skill builds on this primitive.

## Why this exists

Pi-CEO's existing AFK pipeline runs code in `/tmp/pi-ceo-workspaces/{sid}/` git clones — branch isolation only, no container, no resource limits, no permission gating. Acceptable for low-risk autonomy; insufficient for real AFK execution against real production secrets.

Matt Pocock's [Sandcastle](https://github.com/mattpocock/sandcastle) ships container isolation + a parallel-implementer pattern + provider-pluggable agents. We treat it as a binary: one `npx sandcastle run` per code-executing job, parsed via JSON stdout, stdout streamed into existing `session.logs` so the dashboard SSE keeps working unchanged.

## Topology

```
Linear ticket has label sandcastle:high-isolation
  ↓
session_phases.run_build hits its branch point
  ↓
sandcastle_runner.run_sandcastle(SandcastleRunRequest)
  ├── pre-flight: kill_switch.is_active() → abort if true
  ├── pre-flight: active-Sandcastle counter < MAX_CONCURRENT_SANDCASTLE_RUNS
  ├── resolve env-manifest in-memory via vercel-env-puller skill
  ├── write Sandcastle config to /dev/shm/sandcastle-{rid}.json (mode 0600)
  ├── audit_emit.row("sandcastle_run_started", ...)
  ├── asyncio.create_subprocess_exec("npx", "sandcastle", "run", "--config", ...)
  ├── readline-stream stdout → regex-strip secrets → parse_event → session.logs
  ├── on subprocess exit:
  │     ├── parse final RunResult JSON
  │     ├── audit_emit.row("sandcastle_run_ok" | "sandcastle_run_failed", ...)
  │     └── return SandcastleRunResult to caller
  └── finally: os.unlink(/dev/shm/sandcastle-{rid}.json), decrement counter
```

## Contract

### Input

```python
class SandcastleRunRequest:
    session_id: str            # binds to BuildSession.id; logs unify
    agent: Literal["claudeCode","codex","pi","opencode"] = "claudeCode"
    sandbox: Literal["docker","podman","vercel","daytona","noSandbox"] = "docker"
    prompt_template_dir: str   # absolute path to a directory with main.mts + *-prompt.md
    branch: str                # target branch in the cloned repo
    repo_workdir: str          # absolute path to the cloned repo (Pi-CEO supplies this)
    env_manifest_name: str     # name of a `.harness/env-manifests/{name}.json`
    parallel_implementers: int = 1   # passed to parallel-planner-with-review template
    timeout_minutes: int = 30
    extra_env: dict[str, str] = {}   # ad-hoc overrides; never overlap with manifest
    dry_run: bool = False      # uses sandbox="noSandbox" + skip push
```

### Output

```python
class SandcastleRunResult:
    run_id: str
    status: Literal["ok","failed","timeout","killed","skipped"]
    branch: str
    commits: list[dict]        # [{"sha": "..."}]
    merged_branch: str | None
    log_tail: list[str]        # last 50 lines, secret-stripped
    duration_seconds: float
    audit_row_count: int
    skip_reason: str | None    # populated when status=skipped
```

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

## Concurrency

| Setting | Default | Where |
|---|---|---|
| `MAX_CONCURRENT_SANDCASTLE_RUNS` | 3 | `app/server/config.py` |
| Memory floor pre-launch | 4 GB free | `psutil.virtual_memory().available` check |
| Active-run counter | in-memory `app/server/sandcastle_state.py::ACTIVE` | Decremented in `finally` block |

Above the cap, callers receive `status="skipped"`, `skip_reason="concurrency_cap"`. They retry next cycle.

## Pre-flight kill-switch

Before subprocess launch:
1. `kill_switch.is_active()` → if True: return `status="skipped"`, `skip_reason="kill_switch_active"`. Do not even resolve env manifest.
2. `os.environ["TAO_SANDCASTLE_ENABLED"] != "1"` → return `status="skipped"`, `skip_reason="sandcastle_disabled"`.
3. Active counter check.

After subprocess launches:
- Mid-run kill_switch flip → next subprocess output line triggers `proc.terminate()`. After 5 s of no exit, `proc.kill()`. Mirrors `kill_session` in `sessions.py`.
- Audit row `sandcastle_run_failed` with `failure_reason="kill_switch_mid_run"`.

## Stdout handling

Each line from Sandcastle subprocess goes through:

```
raw_line
  → regex_strip_secrets(line)   # [A-Z_]+_(KEY|TOKEN|SECRET|PASSWORD)\s*[=:]\s*\S+ → "***=[REDACTED]"
  → parse_event(line)           # existing function in session_phases.py
  → session.logs.append()       # SSE stream picks it up unchanged
```

Final stdout line should be a JSON `{"type": "run_complete", "result": {...}}`. Parser unmarshals into `SandcastleRunResult`.

## Audit events emitted

Add to `swarm/audit_emit.py::_VALID_TYPES`:

```python
# Wave 5 / RA-1856 — Sandcastle
"sandcastle_run_started",   # one per launch; fields: run_id, agent, sandbox, branch
"sandcastle_run_ok",        # one per successful completion; fields: run_id, duration_s, commits_count
"sandcastle_run_failed",    # one per failure; fields: run_id, failure_reason, exit_code
"sandcastle_env_resolved",  # one per launch; fields: run_id, var_count, project_slug — NAMES NOT VALUES
```

Existing `audit_emit._maybe_redact` handles long-string redaction; we add the regex strip on top for the specific shape `KEY=value` that the redactor's >32-char heuristic might miss for short keys.

## Process supervision

```python
proc = await asyncio.create_subprocess_exec(
    "npx", "sandcastle", "run",
    "--config", config_path,
    "--json",
    cwd=req.repo_workdir,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT,
    env=PROC_ENV,  # PATH only; never includes Pi-CEO secrets
)
```

`PROC_ENV` includes only `PATH`, `HOME`, `NODE_NO_WARNINGS=1`. All secrets enter Sandcastle through the `--config` JSON file (which is on tmpfs and unlinked in `finally`), NOT through `process.env` of the subprocess. This is the bright line: even if Sandcastle misbehaves, `os.environ` was never the channel.

Timeout enforcement via `asyncio.wait_for(proc.wait(), timeout=req.timeout_minutes * 60)`. On timeout: `proc.terminate()` → 5 s grace → `proc.kill()`.

## Workspace placement

| Environment | Worktree path | Reason |
|---|---|---|
| Local | `/tmp/pi-ceo-workspaces/sandcastle/{session_id}/` | Same root as existing weak-sandbox; gc.py covers it |
| Railway | `/tmp/pi-ceo-workspaces/sandcastle/{session_id}/` | Railway tmpfs |
| Vercel sandbox provider | inside microVM, not host | Sandcastle handles internally; we set `bindMount: false` |

## Error taxonomy

| Failure | Status | Action |
|---|---|---|
| Sandcastle binary missing (`npx sandcastle` not found) | `failed` | Log + audit; admin must install |
| Config JSON write failed (tmpfs full) | `failed` | Log + audit; alert |
| Subprocess exit code ≠ 0 | `failed` | Capture `log_tail`, parse stderr if any |
| Timeout reached | `timeout` | terminate → kill; capture partial result |
| Kill-switch flipped mid-run | `killed` | terminate → kill |
| Concurrency cap hit | `skipped` | Caller retries next cycle |
| Env auth failure post-run (regex-detect 401/403) | `ok` (Sandcastle thinks it succeeded) **plus** `cfo_alert` audit row | CFO bot escalates |

## When NOT to use this skill

- Single-tool calls — call the MCP tool directly, no need for container.
- Local dev cycles where you want to see the agent's work synchronously — use Sandcastle's `interactive()` mode directly via CLI.
- Pure research — call `mcp__margot__deep_research` directly.

## Verification (Wave 5 #1 close-out)

1. **Compile + import smoke** — `python -m py_compile app/server/sandcastle_runner.py` green.
2. **Dry-run mode** — invoke with `dry_run=True, sandbox="noSandbox", agent="claudeCode"`. Sandcastle must:
   - return `status="ok"`
   - produce `branch` non-empty
   - have ≥1 entry in `commits`
   - leave ZERO env-var names in `session.logs` after a `grep -E '[A-Z_]+_(KEY|TOKEN|SECRET|PASSWORD)\s*[=:]'`
   - emit ≥3 audit rows (`started`, `env_resolved`, `ok`)
3. **Kill-switch refusal** — set `TAO_SANDCASTLE_ENABLED=0`, call `run_sandcastle()` → returns `status="skipped"`, `skip_reason="sandcastle_disabled"`. No subprocess launch.
4. **Concurrency cap** — fire 4 simultaneous calls → first 3 launch, 4th returns `status="skipped"`, `skip_reason="concurrency_cap"`.
5. **Timeout** — set `timeout_minutes=0.05` (3 s), kick off a long-running prompt → returns `status="timeout"`, subprocess gone within 8 s of timeout fire.
6. **Stdout secret-strip** — synthetic Sandcastle stdout containing `ANTHROPIC_API_KEY=sk-ant-fake-key-for-test` → after `regex_strip_secrets`, the line in `session.logs` reads `ANTHROPIC_API_KEY=***=[REDACTED]` or equivalent. ZERO key-shape strings in logs.

## Out of scope for Wave 5 #1

- Real Vercel-sandbox-provider wire-up (Wave 5 #2 manifest needs to land first)
- TMPFS / FIFO secret injection design details (Wave 5 #3 — `_resolve_env_manifest` is a stub here that returns `{}` until #2/#3 land)
- Margot bridge (Wave 5 #4)
- session_phases.run_build branch point (Wave 5 #6)

This skill ships the contract + the subprocess + the audit. The plumbing on either side comes in subsequent tickets.

## References

- Sandcastle source: https://github.com/mattpocock/sandcastle (MIT, 0.5.7, HEAD May 1 2026)
- Approved plan: `/Users/phill-mac/.claude/plans/breezy-wiggling-map.md`
- Senior-Agent blueprint: `/Users/phill-mac/Pi-CEO/Senior-Agent-Operations-Blueprint-2026-05-02.md`
- Existing kill-switch substrate: `swarm/kill_switch.py`
- Existing audit substrate: `swarm/audit_emit.py`
- Existing session lifecycle: `app/server/sessions.py` + `app/server/session_phases.py`
- Pi-Dev-Ops model-routing policy (RA-1099): `app/server/model_policy.py`
- Parent epic: <issue id="RA-1856">RA-1856</issue>
