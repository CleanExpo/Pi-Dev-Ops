#!/usr/bin/env node
/**
 * route-exercise.mjs — C12. Runtime route exercising for the command-centre surface.
 *
 * WHY THIS REPLACES THE REGEX DETECTOR
 *
 * The old check scanned source for navigation FORMS: href="...", fetch("..."), then
 * router.push("..."), then it would have been <Link href={expr}>, then object hrefs,
 * wrapper components, window.location, server redirects, form actions. Four review rounds
 * each found the next form. Enumerating forms is not a design that can be completed.
 *
 * AST extraction with dataflow was considered and REJECTED for the same reason: you still
 * decide which patterns count, and wrapper components and computed values defeat it
 * identically. It is the same uncompletable enumeration in better clothes.
 *
 * This asks a different question. Not "what forms did we look for" but "what did the
 * surface actually emit". The app is built, started, and its pages are fetched; every
 * internal link in the RENDERED output is then requested and must not 404. `<Link
 * href={d.href}>` over a local array resolves at render time, so it appears in the HTML
 * like any other link — the form it was written in stops mattering.
 *
 * That is the same fact-versus-claim distinction that made operator-gateway a rebuild.
 *
 * SCOPE — what this does NOT cover, stated here rather than discovered in round five:
 *
 *   - Client-side navigation that only happens in an event handler (router.push inside
 *     onClick) does not appear in server-rendered HTML. The cheap literal tripwire in
 *     command-centre-readonly.test.ts still covers the literal spelling of that, and it
 *     is labelled a tripwire precisely because it cannot cover the rest.
 *   - Links that only render behind state this run does not reach (an error branch, a
 *     populated-data branch) are not exercised. Coverage is what rendered, not what could.
 *     Every page fetched is asserted 200 so a page that fails to render cannot pass by
 *     emitting nothing — but a BRANCH that did not render is genuinely unmeasured.
 *   - CLIENT-HYDRATED navigation. This fetches server-rendered HTML; it does not run a
 *     browser or hydrate components. A <Link> that only appears after useEffect, from
 *     localStorage, at a viewport size, or after client data arrives is NOT exercised.
 *     Named by round-1 review as the largest remaining hole and it is a real one: closing it
 *     needs a real browser, which is a different tool with a different cost.
 *   - External links are skipped by design; this asks whether OUR routes exist. Same-origin
 *     is decided by resolving each href against the page URL, so relative and absolute forms
 *     are handled by one rule rather than by a list of spellings.
 *
 * Usage: node scripts/route-exercise.mjs [--plant-broken-link] [--plant-relative-link]
 *   --plant-broken-link    control: assert this script FAILS on a known-bad absolute route.
 *   --plant-relative-link  control: same, for a RELATIVE href with no leading slash.
 */
import { spawn, spawnSync } from "node:child_process";
import { createHmac, randomBytes } from "node:crypto";
import { existsSync, statSync as fsStat, readdirSync as fsRead } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const APP = join(ROOT, "dashboard");
const PORT = process.env.ROUTE_EXERCISE_PORT || "3187";
const BASE = `http://127.0.0.1:${PORT}`;
// Generated per run, never stored. It only has to match what we start the server with, so
// a literal bought nothing and tripped the secrets scanner as a hardcoded password — fairly,
// since a scanner cannot tell a throwaway probe secret from a real one by reading it.
const PASSWORD = randomBytes(24).toString("hex");
const PLANT = process.argv.includes("--plant-broken-link");
// Separate control for the round-2 finding: a RELATIVE internal link. If the extractor ever
// regresses to slash-prefixed-only matching, this stops failing and the regression is loud.
const PLANT_REL = process.argv.includes("--plant-relative-link");

/** Pages whose rendered output defines the navigation surface under test. */
const ENTRY_PAGES = [
  "/command-centre",
  "/command-centre/hermes",
  "/command-centre/knowledge",
  "/command-centre/wiki-graph",
];

const log = (...a) => console.log("   ", ...a);

/**
 * Every request this verifier makes carries a timeout.
 *
 * Review finding, round 1: `waitForServer` and all page/link fetches had no signal, so a
 * wedged listener or a hanging route turned the verifier into SILENCE rather than a loud
 * diagnostic. For a checker that is the worst failure mode — an unbounded hang reads as
 * "still working", and whoever is waiting eventually kills it and moves on with no verdict.
 */
const REQ_TIMEOUT_MS = 15_000;
const get = (url, opts = {}) =>
  fetch(url, { redirect: "manual", signal: AbortSignal.timeout(REQ_TIMEOUT_MS), ...opts });

/** Mint a pi_session cookie the same way app/api/auth/login/route.ts does. */
function mintSession() {
  const issuedAt = String(Math.floor(Date.now() / 1000));
  const sig = createHmac("sha256", PASSWORD).update(issuedAt).digest("hex");
  return `pi_session=${issuedAt}.${sig}`;
}

async function waitForServer(timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await get(BASE + "/");
      if (r.status > 0) return true;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

/**
 * Internal paths in rendered HTML, RESOLVED rather than pattern-matched.
 *
 * Round-2 review: the previous version matched only `href="/..."`, so a rendered relative
 * link — `href="hermes"`, `href="./hermes"`, `href="../knowledge"` — was internal
 * navigation that went unexercised. Adding "also match non-slash hrefs" would have been
 * another pattern on the pile, which is the thing this whole check exists to stop doing.
 *
 * So: take every href/action/formaction value and RESOLVE it against the page it was found
 * on, using the URL parser. Relative, absolute, protocol-relative and external all fall out
 * of one rule — same origin means ours, and `pathname + search` is what to request. URL
 * resolution is decidable and complete in a way form-enumeration never was.
 */
function extractPaths(html, pageUrl) {
  const out = new Set();
  for (const m of html.matchAll(/(?:href|action|formaction)=["']([^"']*)["']/gi)) {
    const raw = m[1].trim();
    if (!raw || raw.startsWith("#")) continue;
    // Non-http schemes are not navigation we can request: mailto:, tel:, javascript:, data:
    if (/^[a-z][a-z0-9+.-]*:/i.test(raw) && !/^https?:/i.test(raw)) continue;
    let u;
    try { u = new URL(raw, pageUrl); } catch { continue; }
    if (u.origin !== new URL(BASE).origin) continue;   // external — not ours to assert
    const p = (u.pathname.replace(/\/$/, "") || "/") + u.search;
    // Framework build assets are not app routes. Their absence IS a real signal — it is how
    // the stale-server bug first showed — but it belongs to build integrity, which
    // `npm run build` already owns.
    if (p.startsWith("/_next/")) continue;
    out.add(p);
  }
  return [...out];
}

/** True if something is already listening on the port. */
async function portInUse() {
  try {
    const r = await fetch(BASE + "/", { redirect: "manual", signal: AbortSignal.timeout(2000) });
    return r.status > 0;
  } catch { return false; }
}

async function main() {
  const buildId = join(APP, ".next", "BUILD_ID");
  if (!existsSync(buildId)) {
    console.error("FAIL: no build found at dashboard/.next — run `npm run build` first.");
    return 2;
  }

  // CONTROL — the build must be newer than the source it claims to represent.
  //
  // Round-1 review: "a stale or wrong build still passes standalone C12 if .next/BUILD_ID
  // exists; only the handoff loop's preceding build gate makes that safe in context." Correct,
  // and relying on call-site ordering is exactly how the stale-SERVER bug happened. A verifier
  // must not be safe only when invoked politely. Same class as the port control: measuring the
  // wrong artifact is indistinguishable from success.
  const buildTime = fsStat(buildId).mtimeMs;
  let newestSrc = 0, newestPath = "";
  for (const dir of ["app", "components", "lib", "proxy.ts"]) {
    (function walk(d) {
      if (!existsSync(d)) return;
      const st = fsStat(d);
      if (st.isFile()) {
        if (st.mtimeMs > newestSrc) { newestSrc = st.mtimeMs; newestPath = d; }
        return;
      }
      for (const e of fsRead(d)) walk(join(d, e));
    })(join(APP, dir));
  }
  if (newestSrc > buildTime) {
    console.error(
      `FAIL: the build is older than the source.
` +
      `      newest source: ${newestPath.slice(APP.length + 1)}
` +
      `      Serving a stale build means exercising routes that are not the ones on disk —
` +
      `      a green run would describe a different app. Rebuild, then re-run.`);
    return 2;
  }
  log("control: build is newer than source — exercising the code that is actually on disk");

  const env = {
    ...process.env,
    NODE_ENV: "production",
    DASHBOARD_PASSWORD: PASSWORD,
    PI_CEO_URL: "https://x.invalid",
    PI_CEO_PASSWORD: "x",
    NEXT_PUBLIC_SUPABASE_URL: "https://lksfwktwtmyznckodsau.supabase.co",
    NEXT_PUBLIC_SUPABASE_ANON_KEY: "x",
    SUPABASE_SERVICE_ROLE_KEY: "x",
  };

  // CONTROL — refuse to attach to a server we did not start.
  //
  // This is not defensive tidiness; it is the control for a false-green this script
  // actually produced. The first version used `shell: true` and `server.kill()`, which on
  // Windows kills the shell and orphans the `next start` grandchild. A later run then found
  // :3187 already answering, attached to a server still serving the PREVIOUS build, and
  // reported that a planted broken route did not exist — measuring one build while claiming
  // to measure another. Caught only because the positive control expected a failure and got
  // a pass. Now: a live port is a hard stop, and the tree is killed properly.
  if (await portInUse()) {
    console.error(
      `FAIL: something is already listening on :${PORT}. Refusing to run — attaching to a\n` +
      `      server this script did not start means measuring an unknown build, which is\n` +
      `      indistinguishable from success. Kill it, or set ROUTE_EXERCISE_PORT.`);
    return 2;
  }

  log(`starting the built app on :${PORT} ...`);
  const server = spawn("npx", ["next", "start", "-p", PORT], {
    cwd: APP, env, shell: true, stdio: ["ignore", "pipe", "pipe"],
    detached: process.platform !== "win32", // own process group, so the group kill works
  });
  let serverLog = "";
  server.stdout.on("data", (d) => { serverLog += d; });
  server.stderr.on("data", (d) => { serverLog += d; });

  // Kill the TREE, SYNCHRONOUSLY. Two bugs were needed to get here and both are worth
  // naming: `server.kill()` alone kills the shell and orphans `next start` on Windows;
  // and an async `spawn("taskkill")` registered on process 'exit' never runs, because
  // Node exits before it starts. spawnSync in `finally` is the only version that works.
  const shutdown = () => {
    try {
      if (process.platform === "win32") {
        spawnSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], { stdio: "ignore" });
      } else {
        // shell:true means `server.pid` is the shell on POSIX too. Kill the process GROUP.
        // Round-1 review flagged that the Windows fix left this half unfixed — the stale
        // server bug was Windows-observed but the defect is not Windows-specific.
        try { process.kill(-server.pid, "SIGKILL"); } catch { server.kill("SIGKILL"); }
      }
    } catch { /* best effort */ }
  };

  try {
    if (!await waitForServer()) {
      console.error("FAIL: server did not become reachable.\n" + serverLog.slice(-1500));
      return 2;
    }
    const cookie = mintSession();

    // Control: the session must actually be accepted. If auth silently rejects it, every
    // page below redirects to login, we extract the login page's links, and the run goes
    // green having exercised nothing. That failure would look exactly like success.
    const probe = await get(BASE + ENTRY_PAGES[0], { headers: { cookie } });
    if (probe.status !== 200) {
      console.error(
        `FAIL: control — ${ENTRY_PAGES[0]} returned ${probe.status} with a minted session, ` +
        `expected 200. Without an accepted session this run would exercise the login page ` +
        `and report success. Refusing to report anything.`);
      return 2;
    }
    log("control: minted session accepted (entry page 200) — the run is measuring the real surface");

    const discovered = new Map(); // path -> Set(pages that linked to it)
    const failures = [];

    for (const page of ENTRY_PAGES) {
      const res = await get(BASE + page, { headers: { cookie } });
      if (res.status !== 200) {
        failures.push(`ENTRY ${page} -> ${res.status} (page did not render; its links are unmeasured)`);
        continue;
      }
      let html = await res.text();
      if (PLANT && page === "/command-centre") {
        html += '<a href="/command-centre/this-route-does-not-exist">planted</a>';
      }
      if (PLANT_REL && page === "/command-centre") {
        // No leading slash. Resolves against /command-centre -> /this-relative-route-404s.
        html += '<a href="this-relative-route-404s">planted-relative</a>';
      }
      for (const p of extractPaths(html, BASE + page)) {
        if (!discovered.has(p)) discovered.set(p, new Set());
        discovered.get(p).add(page);
      }
    }

    log(`rendered ${ENTRY_PAGES.length} pages, discovered ${discovered.size} distinct internal paths`);

    for (const [path, sources] of [...discovered].sort()) {
      const res = await get(BASE + path, { headers: { cookie } });
      if (res.status === 404) {
        failures.push(`404  ${path}   (linked from: ${[...sources].join(", ")})`);
      } else if (res.status >= 500) {
        failures.push(`${res.status}  ${path}   (linked from: ${[...sources].join(", ")})`);
      }
    }

    if (failures.length) {
      console.error("\nFAIL — internal navigation that does not resolve:\n");
      for (const f of failures) console.error("  " + f);
      return 1;
    }
    log(`OK — every rendered internal link resolves (${discovered.size} paths exercised)`);
    return 0;
  } finally {
    shutdown();
  }
}

main().then((c) => process.exit(c)).catch((e) => {
  console.error("FAIL: route-exercise crashed:", e);
  process.exit(2);
});
