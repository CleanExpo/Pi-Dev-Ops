#!/usr/bin/env node
// Strict Unlazy gate checker: exit status AND expectation must pass.
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import process from "node:process";

const MAX_JOBS = 8;
const MAX_OUTPUT = 64 * 1024;
const RUNNER_VERSION = "nexus-unlazy-gate-v3";
const DEFAULT_ENV_KEYS = ["PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "TERM", "CI"];
const SENSITIVE_ENV_KEY = /(?:^|_)(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS?)(?:_|$)/i;
const SECRET = /(sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+|(?:api[_-]?key|token|secret|password)\s*[=:]\s*\S+)/gi;

function usage() {
  console.error("usage: unlazy-gate-check.mjs [--status] [--json] [--jobs N] [--cwd DIR] --plan-id ID --node-id ID --worker-id ID --verifier-id ID --relevant-input PATH GATES.md [...]");
}

function parseArgs(argv) {
  const out = {
    status: false,
    json: false,
    jobs: 1,
    cwd: process.cwd(),
    envKeys: [],
    planId: "",
    nodeId: "",
    workerId: "",
    verifierId: "",
    relevantInputs: [],
    files: [],
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--status") out.status = true;
    else if (arg === "--json") out.json = true;
    else if (arg === "--jobs") out.jobs = Number(argv[++index]);
    else if (arg === "--cwd") out.cwd = argv[++index];
    else if (arg === "--env") out.envKeys.push(argv[++index]);
    else if (arg === "--plan-id") out.planId = argv[++index] || "";
    else if (arg === "--node-id") out.nodeId = argv[++index] || "";
    else if (arg === "--worker-id") out.workerId = argv[++index] || "";
    else if (arg === "--verifier-id") out.verifierId = argv[++index] || "";
    else if (arg === "--relevant-input") out.relevantInputs.push(argv[++index] || "");
    else if (arg.startsWith("-")) throw new Error(`unknown option ${arg}`);
    else out.files.push(arg);
  }
  if (!Number.isInteger(out.jobs) || out.jobs < 1 || out.jobs > MAX_JOBS) {
    throw new Error(`--jobs must be an integer from 1 to ${MAX_JOBS}`);
  }
  if (!out.files.length) throw new Error("at least one gate file is required");
  if (!out.status && (!out.planId || !out.nodeId || !out.workerId || !out.verifierId)) {
    throw new Error("--plan-id, --node-id, --worker-id, and --verifier-id are required for a verified run");
  }
  if (!out.status && out.workerId === out.verifierId) {
    throw new Error("--verifier-id must differ from --worker-id for an independent verified run");
  }
  if (!out.status && !out.relevantInputs.length) {
    throw new Error("at least one --relevant-input is required for a verified run");
  }
  if (out.envKeys.some((key) => SENSITIVE_ENV_KEY.test(key))) {
    throw new Error("sensitive environment keys cannot be allow-listed for gate commands");
  }
  return out;
}

function digestFiles(root, files) {
  const entries = [...new Set(files)].sort().map((file) => ({
    path: relative(root, file),
    digest: `sha256:${createHash("sha256").update(readFileSync(file)).digest("hex")}`,
  }));
  const payload = entries.map((entry) => `${entry.path}\0${entry.digest}`).join("\0");
  return {
    entries,
    digest: `sha256:${createHash("sha256").update(payload).digest("hex")}`,
  };
}

function repositoryRoot(cwd) {
  return execFileSync("git", ["rev-parse", "--show-toplevel"], { cwd, encoding: "utf8" }).trim();
}

function repositoryHead(cwd) {
  return execFileSync("git", ["rev-parse", "HEAD"], { cwd, encoding: "utf8" }).trim();
}

function repositoryBase(cwd) {
  try {
    return execFileSync("git", ["merge-base", "origin/main", "HEAD"], {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return null;
  }
}

function repositoryStatus(cwd) {
  return execFileSync(
    "git",
    ["status", "--porcelain=v1", "--untracked-files=all"],
    { cwd, encoding: "utf8" },
  ).trim();
}

function commandEnvironment(extraKeys) {
  const keys = [...new Set([...DEFAULT_ENV_KEYS, ...extraKeys])].filter(Boolean).sort();
  const env = {};
  for (const key of keys) {
    if (Object.hasOwn(process.env, key)) env[key] = process.env[key];
  }
  const digestPayload = keys.map((key) => `${key}=${env[key] ?? "<unset>"}`).join("\0");
  return {
    keys,
    env,
    digest: `sha256:${createHash("sha256").update(digestPayload).digest("hex")}`,
  };
}

function inside(root, target) {
  const rel = relative(realpathSync(root), realpathSync(target));
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel));
}

function parseGateFile(path) {
  const lines = readFileSync(path, "utf8").split(/\r?\n/);
  const abandoned = new Map();
  for (const line of lines) {
    const match = line.match(/^\s*ABANDON:\s*([A-Za-z0-9_.-]+)\s+(.+)$/);
    if (match) abandoned.set(match[1], match[2].trim());
  }
  const gates = [];
  let current = null;
  for (let index = 0; index < lines.length; index += 1) {
    const start = lines[index].match(/^\s*-\s*\[([ xX])\]\s*([A-Za-z0-9_.-]+):\s*(.+)$/);
    if (start) {
      current = {
        file: path,
        line: index + 1,
        checked: start[1].toLowerCase() === "x",
        id: start[2],
        outcome: start[3].trim(),
        check: null,
        exits: [0],
        expect: null,
        timeout: 60,
        evidence: "pending",
        abandoned: abandoned.get(start[2]) || null,
      };
      gates.push(current);
      continue;
    }
    if (!current) continue;
    const property = lines[index].match(/^\s+(CHECK|EXIT|EXPECT|TIMEOUT|EVIDENCE):\s*(.*)$/);
    if (!property) continue;
    const [, key, value] = property;
    if (key === "CHECK") current.check = value.trim();
    else if (key === "EXIT") {
      const values = value.split(",").map((item) => Number(item.trim()));
      if (!values.length || values.some((item) => !Number.isInteger(item))) {
        current.parseError = `invalid EXIT at ${path}:${index + 1}`;
      } else current.exits = values;
    } else if (key === "EXPECT") current.expect = value.trim();
    else if (key === "TIMEOUT") {
      const seconds = Number(value.trim());
      if (!Number.isInteger(seconds) || seconds < 1 || seconds > 3600) {
        current.parseError = `invalid TIMEOUT at ${path}:${index + 1}`;
      } else current.timeout = seconds;
    } else if (key === "EVIDENCE") current.evidence = value.trim();
  }
  return gates;
}

function expectationMatches(expectation, output) {
  if (!expectation) return { matched: true, error: null };
  if (expectation.startsWith("/") && expectation.endsWith("/") && expectation.length > 2) {
    try {
      return { matched: new RegExp(expectation.slice(1, -1)).test(output), error: null };
    } catch (error) {
      return { matched: false, error: `invalid EXPECT regex: ${error.message}` };
    }
  }
  return { matched: output.includes(expectation), error: null };
}

function bounded(text) {
  return text.slice(-MAX_OUTPUT).replace(SECRET, "[REDACTED]");
}

function runCommand(command, cwd, timeoutSeconds, env) {
  return new Promise((resolveResult) => {
    const started = Date.now();
    const processGroup = process.platform !== "win32";
    const child = spawn(command, { cwd, shell: true, env, detached: processGroup });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let forceKillTimer = null;
    const terminate = (signal) => {
      try {
        if (processGroup && child.pid) process.kill(-child.pid, signal);
        else child.kill(signal);
      } catch (error) {
        if (error.code !== "ESRCH") throw error;
      }
    };
    child.stdout.on("data", (chunk) => { stdout = bounded(stdout + chunk.toString()); });
    child.stderr.on("data", (chunk) => { stderr = bounded(stderr + chunk.toString()); });
    const timer = setTimeout(() => {
      timedOut = true;
      terminate("SIGTERM");
      forceKillTimer = setTimeout(() => terminate("SIGKILL"), 250);
    }, timeoutSeconds * 1000);
    child.on("error", (error) => {
      clearTimeout(timer);
      resolveResult({ exitCode: null, stdout, stderr, timedOut, runnerError: error.message, elapsedMs: Date.now() - started });
    });
    child.on("close", (code, signal) => {
      clearTimeout(timer);
      if (!timedOut && forceKillTimer) clearTimeout(forceKillTimer);
      resolveResult({
        exitCode: code,
        stdout,
        stderr,
        timedOut,
        runnerError: timedOut ? `timeout after ${timeoutSeconds}s` : signal ? `terminated by ${signal}` : null,
        elapsedMs: Date.now() - started,
      });
    });
  });
}

function outputEvidence(result) {
  const stdout = bounded(result.stdout);
  const stderr = bounded(result.stderr);
  const lines = `${stdout}\n${stderr}`.split(/\r?\n/).filter(Boolean).slice(-2);
  return {
    stdoutDigest: `sha256:${createHash("sha256").update(stdout).digest("hex")}`,
    stderrDigest: `sha256:${createHash("sha256").update(stderr).digest("hex")}`,
    safeSummary: lines.join(" | ").slice(-400),
  };
}

async function runPool(items, jobs, runner) {
  const results = new Array(items.length);
  let next = 0;
  async function worker() {
    while (true) {
      const index = next++;
      if (index >= items.length) return;
      results[index] = await runner(items[index]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(jobs, items.length) }, worker));
  return results;
}

function statusResult(gate) {
  if (gate.parseError) return { ...gate, state: "runner_error", runnerError: gate.parseError };
  if (gate.abandoned) return { ...gate, state: "abandoned" };
  if (gate.checked && gate.evidence && gate.evidence.toLowerCase() !== "pending") {
    return { ...gate, state: "passed" };
  }
  return { ...gate, state: "pending" };
}

async function executeGate(
  gate, cwd, cache, environment, candidateSha, root, relevantFiles, identityBinding,
) {
  if (gate.parseError || gate.abandoned) return statusResult(gate);
  if (!gate.check) return { ...gate, state: "pending" };
  const expectedBeforeRun = expectationMatches(gate.expect, "");
  if (expectedBeforeRun.error) {
    return { ...gate, state: "runner_error", runnerError: expectedBeforeRun.error };
  }
  const relevantInputs = digestFiles(root, relevantFiles);
  const key = `${RUNNER_VERSION}\0${candidateSha}\0${cwd}\0${environment.digest}\0${identityBinding}\0${relevantInputs.digest}\0${gate.check}\0${gate.timeout}`;
  if (!cache.has(key)) cache.set(key, runCommand(gate.check, cwd, gate.timeout, environment.env));
  const result = await cache.get(key);
  const combined = `${result.stdout}\n${result.stderr}`;
  const expected = expectationMatches(gate.expect, combined);
  const evidence = outputEvidence(result);
  if (result.runnerError || expected.error) {
    return {
      ...gate,
      exitCode: result.exitCode,
      timedOut: result.timedOut,
      elapsedMs: result.elapsedMs,
      ...evidence,
      state: "runner_error",
      runnerError: result.runnerError || expected.error,
    };
  }
  const exitAllowed = gate.exits.includes(result.exitCode);
  return {
    ...gate,
    exitCode: result.exitCode,
    timedOut: result.timedOut,
    elapsedMs: result.elapsedMs,
    ...evidence,
    commandDigest: `sha256:${createHash("sha256").update(key).digest("hex")}`,
    relevantInputDigest: relevantInputs.digest,
    expectMatched: expected.matched,
    state: exitAllowed && expected.matched ? "passed" : "failed",
  };
}

function summarise(results) {
  const summary = { passed: 0, failed: 0, pending: 0, abandoned: 0, runner_errors: 0 };
  for (const result of results) {
    if (result.state === "runner_error") summary.runner_errors += 1;
    else summary[result.state] += 1;
  }
  return summary;
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
    const root = repositoryRoot(args.cwd);
    const candidateSha = repositoryHead(args.cwd);
    const baseSha = repositoryBase(args.cwd);
    const environment = commandEnvironment(args.envKeys);
    const cwd = resolve(args.cwd);
    if (!inside(root, cwd)) throw new Error(`cwd must be inside repository: ${cwd}`);
    const worktreeStatus = repositoryStatus(cwd);
    const worktreeClean = worktreeStatus === "";
    if (!args.status && !worktreeClean) {
      throw new Error(
        "worktree must be clean before verified run (tracked or untracked changes present)",
      );
    }
    const files = args.files.map((file) => resolve(cwd, file));
    for (const file of files) {
      if (!inside(root, file)) throw new Error(`gate file must be inside repository: ${file}`);
    }
    const relevantFiles = args.relevantInputs.map((file) => resolve(cwd, file));
    for (const file of relevantFiles) {
      if (!inside(root, file)) throw new Error(`relevant input must be inside repository: ${file}`);
    }
    const identityBinding = [
      args.planId,
      args.nodeId,
      args.workerId,
      args.verifierId,
    ].join("\0");
    const gates = files.flatMap(parseGateFile);
    if (!gates.length) throw new Error("no gates found");
    const cache = new Map();
    const startedAt = new Date().toISOString();
    const results = args.status
      ? gates.map(statusResult)
      : await runPool(gates, args.jobs, (gate) => executeGate(
        gate, cwd, cache, environment, candidateSha, root, relevantFiles, identityBinding,
      ));
    const summary = summarise(results);
    const relevantInputs = digestFiles(root, relevantFiles);
    const receipt = {
      schema_version: "1.0",
      mode: args.status ? "status" : "run",
      verified: !args.status,
      runner_version: RUNNER_VERSION,
      plan_id: args.planId || null,
      node_id: args.nodeId || null,
      worker_id: args.workerId || null,
      verifier_id: args.verifierId || null,
      independent_verifier: Boolean(args.verifierId && args.verifierId !== args.workerId),
      started_at: startedAt,
      finished_at: new Date().toISOString(),
      base_sha: baseSha,
      candidate_sha: candidateSha,
      worktree_clean_before_run: worktreeClean,
      cwd,
      environment_keys: environment.keys,
      environment_digest: environment.digest,
      relevant_inputs: relevantInputs.entries,
      relevant_input_digest: relevantInputs.digest,
      gate_files: files.map((file) => ({
        path: relative(root, file),
        digest: `sha256:${createHash("sha256").update(readFileSync(file)).digest("hex")}`,
      })),
      summary,
      gates: results,
    };
    if (args.json) console.log(JSON.stringify(receipt, null, 2));
    else {
      for (const result of results) console.log(`${result.state.toUpperCase()} ${result.id} ${result.outcome}`);
      console.log(`passed=${summary.passed} failed=${summary.failed} pending=${summary.pending} abandoned=${summary.abandoned} runner_errors=${summary.runner_errors}`);
    }
    if (summary.runner_errors) return 2;
    return summary.failed || summary.pending || summary.abandoned ? 1 : 0;
  } catch (error) {
    if (!args) usage();
    console.error(`unlazy gate checker: ${error.message}`);
    return 2;
  }
}

process.exitCode = await main();
