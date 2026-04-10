/**
 * create-sandbox-snapshot.ts — Vercel Sandbox snapshot creator (RA-541)
 *
 * Creates a pre-built sandbox VM image with Chromium + agent-browser installed,
 * so browser automation tasks start in <1s instead of ~30s cold-start.
 *
 * Usage:
 *   npm run create-snapshot
 *   # or: npx tsx scripts/create-sandbox-snapshot.ts
 *
 * Required env vars (for local use — auto-detected on Vercel via OIDC):
 *   VERCEL_TOKEN      — personal access token with sandbox:write scope
 *   VERCEL_TEAM_ID    — team slug or ID (e.g. team_xxx)
 *   VERCEL_PROJECT_ID — project ID (e.g. prj_xxx)
 *
 * Output:
 *   Prints the snapshot ID. Set it as AGENT_BROWSER_SNAPSHOT_ID in Vercel
 *   project settings to enable fast browser automation in API routes.
 */

import { Sandbox } from "@vercel/sandbox";

// System libraries required by Chromium on the sandbox VM (Amazon Linux / dnf)
const CHROMIUM_SYSTEM_DEPS = [
  "nss", "nspr", "libxkbcommon", "atk", "at-spi2-atk", "at-spi2-core",
  "libXcomposite", "libXdamage", "libXrandr", "libXfixes", "libXcursor",
  "libXi", "libXtst", "libXScrnSaver", "libXext", "mesa-libgbm", "libdrm",
  "mesa-libGL", "mesa-libEGL", "cups-libs", "alsa-lib", "pango", "cairo",
  "gtk3", "dbus-libs",
];

function getCredentials() {
  const { VERCEL_TOKEN, VERCEL_TEAM_ID, VERCEL_PROJECT_ID } = process.env;
  if (VERCEL_TOKEN && VERCEL_TEAM_ID && VERCEL_PROJECT_ID) {
    return { token: VERCEL_TOKEN, teamId: VERCEL_TEAM_ID, projectId: VERCEL_PROJECT_ID };
  }
  // On Vercel, OIDC auth is automatic — no explicit credentials needed
  return {};
}

async function createSnapshot(): Promise<string> {
  console.log("Creating Vercel Sandbox VM (node24, 5 min timeout)…");
  const sandbox = await Sandbox.create({
    ...getCredentials(),
    runtime: "node24",
    timeout: 300_000,
  });

  console.log("Installing Chromium system dependencies via dnf…");
  await sandbox.runCommand("sh", [
    "-c",
    `sudo dnf clean all 2>&1 && sudo dnf install -y --skip-broken ${CHROMIUM_SYSTEM_DEPS.join(" ")} 2>&1 && sudo ldconfig 2>&1`,
  ]);

  console.log("Installing agent-browser globally…");
  await sandbox.runCommand("npm", ["install", "-g", "agent-browser"]);

  console.log("Installing Chromium via agent-browser…");
  await sandbox.runCommand("npx", ["agent-browser", "install"]);

  console.log("Verifying installation…");
  const versionResult = await sandbox.runCommand("agent-browser", ["--version"]);
  const version = await versionResult.stdout();
  console.log(`agent-browser version: ${version.trim()}`);

  console.log("Creating snapshot…");
  const snapshot = await sandbox.snapshot();

  await sandbox.stop();

  return snapshot.snapshotId;
}

async function main() {
  try {
    const snapshotId = await createSnapshot();
    console.log("\n✓ Snapshot created successfully");
    console.log(`  Snapshot ID: ${snapshotId}`);
    console.log("\nNext steps:");
    console.log("  1. Go to Vercel project settings → Environment Variables");
    console.log(`  2. Add: AGENT_BROWSER_SNAPSHOT_ID = ${snapshotId}`);
    console.log("  3. Redeploy to apply the new snapshot");
  } catch (err) {
    console.error("Snapshot creation failed:", err);
    process.exit(1);
  }
}

main();
