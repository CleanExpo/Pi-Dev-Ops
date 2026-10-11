---
name: sandcastle-runner
description: Wraps a single Sandcastle job (`npx --no-install tsx .sandcastle/sandcastle_run.mts`, pinned @ai-hero/sandcastle@0.12.0 `run()` API) so the Pi-CEO orchestrator can spawn AFK code-executing agents in isolated Docker, Podman, Vercel Firecracker or Daytona sandboxes, with pluggable agent and sandbox, a kill-switch check, a concurrency cap and stdout streamed into session.logs. Use for Linear tickets labelled sandcastle:high-isolation and parallel implementer or reviewer runs.
owner_role: Builder
status: wave-5
---

# sandcastle-runner

The Pi-CEO ↔ Sandcastle bridge. One subprocess boundary. Every other Wave 5 skill builds on this primitive.

## Why this exists

Pi-CEO's existing AFK pipeline runs code in `/tmp/pi-ceo-workspaces/{sid}/` git clones — branch isolation only, no container, no resource limits, no permission gating. Acceptable for low-risk autonomy; insufficient for real AFK execution against real production secrets.

Matt Pocock's [Sandcastle](https://github.com/mattpocock/sandcastle) ships container isolation + a parallel-implementer pattern + provider-pluggable agents. One `npx --no-install tsx .sandcastle/sandcastle_run.mts <config.json>` per code-executing job, parsed via its one-line JSON stdout, agent output streamed into existing `session.logs` so the dashboard SSE keeps working unchanged.

**Never call bare `npx sandcastle`.** `@ai-hero/sandcastle` has no `run` command (its CLI is only `init` and `docker|podman build-image|remove-image`), and the unscoped npm name `sandcastle` is an unrelated 2022 package that `npx` would download and execute.

The runner source is `scripts/sandcastle_run.mts` in Pi-Dev-Ops. `scripts/sandcastle-bootstrap.sh` copies it into the target repo's `.sandcastle/` on every run, because it must import `@ai-hero/sandcastle` from that repo's `node_modules` (Pi-Dev-Ops has no `package.json`). It is `.mts` because the package is ESM-only.

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
  ├── asyncio.create_subprocess_exec("npx", "--no-install", "tsx", ".sandcastle/sandcastle_run.mts", config_path)
  ├── readline-stream stderr (status lines) → regex-strip secrets → session.logs
  ├── on subprocess exit:
  │     ├── parse final RunResult JSON from stdout only (exactly one line)
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

Read references/selection-rules.md when choosing a sandbox provider or an agent provider for a run.

## Selection rules — agent provider

Read references/selection-rules.md when choosing a sandbox provider or an agent provider for a run.

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

Read references/audit-events.md when adding or reviewing the sandcastle audit event types.

## Process supervision

```python
proc = await asyncio.create_subprocess_exec(
    "npx", "--no-install", "tsx", ".sandcastle/sandcastle_run.mts", config_path,
    cwd=req.repo_workdir,
    stdout=asyncio.subprocess.PIPE,   # exactly one line: the run_complete JSON
    stderr=asyncio.subprocess.PIPE,   # Sandcastle status lines; stream to session.logs
    env=PROC_ENV,  # PATH only; never includes Pi-CEO secrets
)
```

Keep the two pipes separate. Sandcastle prints status lines ("[Agent] Started on branch ...", "tail -f <log>"), which the runner routes to stderr; merging stderr into stdout breaks `json.loads` on the result line.

`PROC_ENV` includes only `PATH`, `HOME`, `NODE_NO_WARNINGS=1` and `TAO_HARD_STOP_FILE`. All secrets enter Sandcastle through the config JSON file (which is on tmpfs and unlinked in `finally`), NOT through `process.env` of the subprocess. This is the bright line: even if Sandcastle misbehaves, `os.environ` was never the channel.

Config keys (see the header of `scripts/sandcastle_run.mts`): `cwd`, `prompt` or `promptFile`, `model`, `branch` (required; passed as `branchStrategy: {type: "branch"}` so a job never merges into the host checkout's current branch, which is `run()`'s default; refused if it equals the host checkout's current branch), `sandbox`, `sandboxOptions` (e.g. `{"imageName": ...}` — `imageName` lives in the provider since 0.6), `agentEnv`, `sandboxEnv` (key sets MUST be disjoint — `run()` throws on overlap), `maxIterations`, `idleTimeoutSeconds` (default 600), `completionTimeoutSeconds` (default 60), `killSwitchFiles` (pass `.harness/swarm/kill_switch.flag`). Sandcastle's `run()` also auto-loads `<cwd>/.sandcastle/.env` into the job, bypassing those maps, so the runner refuses to start (exit 2) while that file exists. `noSandbox` runs the agent on the host with no isolation, so the runner refuses it (exit 2) unless the config sets `allowUnisolated: true`; use that only for dry-run and smoke tests. The result carries `isolated`.

The runner uses `claudeCode(model, { permissionMode: "auto" })` — never a skip-permissions flag. It polls `TAO_HARD_STOP_FILE` (default `~/.claude/HARD_STOP`) and every `killSwitchFiles` entry each second and aborts `run()` through its `signal`; SIGTERM/SIGINT abort it the same way. `run()` has no concurrency cap, so `MAX_CONCURRENT_SANDCASTLE_RUNS` stays with the caller.

Exit codes: `0` ok · `1` failed · `2` bad usage/config · `3` killed. stdout is exactly one line, `{"type":"run_complete","result":{"status": ..., "branch", "commits", "iterations", "logFilePath", ...}}`; agent output goes to `result.logFilePath`. `iterations` is a count (`RunResult.iterations.length`; 0.5.7's `iterationsRun` no longer exists).

Timeout enforcement via `asyncio.wait_for(proc.wait(), timeout=req.timeout_minutes * 60)`. On timeout: `proc.terminate()` → 5 s grace → `proc.kill()`.

## Workspace placement

Read references/workspace-placement.md when deciding where a Sandcastle worktree lives per environment.

## Error taxonomy

| Failure | Status | Action |
|---|---|---|
| Runner or package missing (`.sandcastle/sandcastle_run.mts` or `node_modules/@ai-hero/sandcastle` absent) | `failed` | Log + audit; re-run `scripts/sandcastle-bootstrap.sh` |
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

Read references/verification.md when closing out or re-verifying the runner, or checking what is out of scope.

## Out of scope for Wave 5 #1

Read references/verification.md when closing out or re-verifying the runner, or checking what is out of scope.

## References

- Sandcastle source: https://github.com/mattpocock/sandcastle (MIT, pinned 0.12.0, released 2026-06-29)
- Approved plan: `~/.claude/plans/breezy-wiggling-map.md`
- Senior-Agent blueprint: `~/Pi-CEO/Senior-Agent-Operations-Blueprint-2026-05-02.md`
- Existing kill-switch substrate: `swarm/kill_switch.py`
- Existing audit substrate: `swarm/audit_emit.py`
- Existing session lifecycle: `app/server/sessions.py` + `app/server/session_phases.py`
- Pi-Dev-Ops model-routing policy (RA-1099): `app/server/model_policy.py`
- Parent epic: <issue id="RA-1856">RA-1856</issue>
