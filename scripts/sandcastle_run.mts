/**
 * sandcastle_run.mts — UNI-2926 (replaces the non-existent `npx sandcastle run`).
 *
 * Runs ONE Sandcastle job through the pinned @ai-hero/sandcastle@0.12.0 JS API
 * (`run()`), because the package's CLI has no `run` command. Never call bare
 * `npx sandcastle`: the unscoped npm name is an unrelated package.
 *
 * Usage:  npx --no-install tsx .sandcastle/sandcastle_run.mts <config.json>
 *         (bootstrap installs the pinned tsx locally; --no-install stops npx fetching one)
 *
 * `.mts` on purpose: the package is ESM-only, and a `.ts` file under a default
 * (CommonJS) package.json cannot import it.
 *
 * The config file is written by the caller on tmpfs (mode 0600) and unlinked by
 * the caller afterwards. Secrets travel in it, never through process.env.
 *
 * stdout carries exactly one line: {"type":"run_complete","result":{...}}.
 * Agent output goes to the Sandcastle log file (result.logFilePath).
 *
 * Exit codes: 0 ok · 1 failed · 2 bad usage/config · 3 killed by kill-switch.
 *
 * Concurrency: run() has no cap. The caller (sandcastle-runner) keeps the
 * MAX_CONCURRENT_SANDCASTLE_RUNS counter; this script runs exactly one job.
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { claudeCode, run, type SandboxProvider } from "@ai-hero/sandcastle";

type SandboxName = "docker" | "podman" | "noSandbox" | "vercel" | "daytona";

interface RunConfig {
  cwd: string;
  prompt?: string;
  promptFile?: string;
  model: string;
  /** Named branch the job commits to. Required: without it run() defaults to
   *  merge-to-head (isolated) or head (bind-mount) and writes into the host's
   *  current branch. */
  branch: string;
  sandbox: SandboxName;
  /** Provider options, e.g. { imageName } for docker/podman (moved here in 0.6+). */
  sandboxOptions?: Record<string, unknown>;
  /** Env for the agent process. Keys MUST NOT overlap sandboxEnv — run() throws. */
  agentEnv?: Record<string, string>;
  /** Env for the sandbox. Keys MUST NOT overlap agentEnv — run() throws. */
  sandboxEnv?: Record<string, string>;
  maxIterations?: number;
  idleTimeoutSeconds?: number;
  completionTimeoutSeconds?: number;
  /** Extra flag files whose existence aborts the run (e.g. .harness/swarm/kill_switch.flag). */
  killSwitchFiles?: string[];
  /** Must be exactly true for sandbox "noSandbox", which runs the agent on the host. Dry-run/smoke only. */
  allowUnisolated?: boolean;
}

const PROVIDER_MODULES: Record<SandboxName, [string, string]> = {
  docker: ["@ai-hero/sandcastle/sandboxes/docker", "docker"],
  podman: ["@ai-hero/sandcastle/sandboxes/podman", "podman"],
  noSandbox: ["@ai-hero/sandcastle/sandboxes/no-sandbox", "noSandbox"],
  vercel: ["@ai-hero/sandcastle/sandboxes/vercel", "vercel"],
  daytona: ["@ai-hero/sandcastle/sandboxes/daytona", "daytona"],
};

const KILL_POLL_MS = 1000;

// stdout belongs to the one JSON result line. Sandcastle prints status lines
// ("[Agent] Started on branch ...", "tail -f <log>") with console.log, so every
// other in-process stdout write is routed to stderr.
const writeResult = process.stdout.write.bind(process.stdout);
process.stdout.write = process.stderr.write.bind(process.stderr) as typeof process.stdout.write;

function emit(status: string, exitCode: number, extra: Record<string, unknown>): never {
  writeResult(JSON.stringify({ type: "run_complete", result: { status, ...extra } }) + "\n");
  process.exit(exitCode);
}

function loadConfig(path: string | undefined): RunConfig {
  if (!path) emit("failed", 2, { error: "usage: sandcastle_run.mts <config.json>" });
  const cfg = JSON.parse(readFileSync(path, "utf8")) as RunConfig;
  if (!cfg.cwd || !cfg.model || !Object.hasOwn(PROVIDER_MODULES, cfg.sandbox)) {
    emit("failed", 2, { error: "config needs cwd, model and a known sandbox" });
  }
  if (typeof cfg.branch !== "string" || !cfg.branch.trim()) {
    emit("failed", 2, { error: "config needs a non-empty branch (never the host's current branch)" });
  }
  if (cfg.branch === hostBranch(cfg.cwd)) {
    emit("failed", 2, { error: `branch ${cfg.branch} is the host checkout's current branch` });
  }
  if (cfg.sandbox === "noSandbox" && cfg.allowUnisolated !== true) {
    emit("failed", 2, { error: "noSandbox runs on the host with no isolation; set allowUnisolated: true (dry-run/smoke only)" });
  }
  if (!cfg.prompt === !cfg.promptFile) {
    emit("failed", 2, { error: "config needs exactly one of prompt / promptFile" });
  }
  return cfg;
}

/** The host checkout's current branch, or null when detached / not a repo. */
function hostBranch(cwd: string): string | null {
  try {
    return execFileSync("git", ["-C", cwd, "symbolic-ref", "--quiet", "--short", "HEAD"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

/** Same flags the Python kill switches read: TAO_HARD_STOP_FILE plus caller-supplied ones. */
function killSwitchFiles(cfg: RunConfig): string[] {
  const hardStop = process.env.TAO_HARD_STOP_FILE || join(homedir(), ".claude", "HARD_STOP");
  return [hardStop, ...(cfg.killSwitchFiles ?? [])];
}

async function loadSandbox(cfg: RunConfig): Promise<SandboxProvider> {
  const [mod, name] = PROVIDER_MODULES[cfg.sandbox];
  const factory = (await import(mod))[name] as (o: object) => SandboxProvider;
  return factory({ ...(cfg.sandboxOptions ?? {}), env: cfg.sandboxEnv ?? {} });
}

async function main(): Promise<void> {
  const cfg = loadConfig(process.argv[2]);
  const controller = new AbortController();
  const files = killSwitchFiles(cfg);
  const checkKill = (): void => {
    const hit = files.find((f) => existsSync(f));
    if (hit && !controller.signal.aborted) controller.abort(new Error(`kill_switch: ${hit}`));
  };
  checkKill();
  if (controller.signal.aborted) emit("killed", 3, { error: String(controller.signal.reason) });
  const poll = setInterval(checkKill, KILL_POLL_MS);
  for (const sig of ["SIGTERM", "SIGINT"] as const) {
    process.on(sig, () => controller.abort(new Error(`signal: ${sig}`)));
  }
  try {
    const result = await run({
      agent: claudeCode(cfg.model, { permissionMode: "auto", env: cfg.agentEnv ?? {} }),
      sandbox: await loadSandbox(cfg),
      cwd: cfg.cwd,
      branchStrategy: { type: "branch", branch: cfg.branch },
      ...(cfg.prompt ? { prompt: cfg.prompt } : { promptFile: cfg.promptFile }),
      maxIterations: cfg.maxIterations ?? 1,
      idleTimeoutSeconds: cfg.idleTimeoutSeconds ?? 600,
      completionTimeoutSeconds: cfg.completionTimeoutSeconds ?? 60,
      signal: controller.signal,
    });
    emit("ok", 0, {
      isolated: cfg.sandbox !== "noSandbox",
      branch: result.branch,
      commits: result.commits,
      iterations: result.iterations.length,
      completionSignal: result.completionSignal ?? null,
      logFilePath: result.logFilePath ?? null,
      preservedWorktreePath: result.preservedWorktreePath ?? null,
    });
  } catch (err) {
    clearInterval(poll);
    if (controller.signal.aborted) emit("killed", 3, { error: String(controller.signal.reason) });
    emit("failed", 1, { error: err instanceof Error ? err.message : String(err) });
  }
}

void main();
