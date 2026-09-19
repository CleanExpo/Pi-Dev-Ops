import { execFileSync } from "child_process";

const ROUTING_OVERRIDES = [
  "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
  "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
];
const SHELL_ENV = [
  "PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SystemRoot",
  "SYSTEMROOT", "TEMP", "TMP", "LANG", "CLAUDE_CONFIG_DIR",
];

export function requireApiTransport(): void {
  throw new Error("Subscription-only policy: paid or unverified API transport is blocked.");
}

/** Verify the current login without exporting dashboard credentials to the CLI. */
export function requireSubscriptionCLI(): NodeJS.ProcessEnv {
  if (ROUTING_OVERRIDES.some((key) => process.env[key]?.trim())) {
    throw new Error("Subscription-only policy: API credentials or provider overrides are present.");
  }
  const env: NodeJS.ProcessEnv = { NODE_ENV: process.env.NODE_ENV };
  for (const key of SHELL_ENV) if (process.env[key] !== undefined) env[key] = process.env[key];
  try {
    const status = JSON.parse(execFileSync("claude", ["auth", "status", "--json"], {
      env, encoding: "utf8", timeout: 10_000, windowsHide: true, stdio: ["ignore", "pipe", "pipe"],
    }));
    if (status?.loggedIn === true && status.authMethod === "claude.ai"
      && ["max", "pro", "team", "enterprise"].includes(status.subscriptionType)) return env;
  } catch { /* Missing, malformed or unavailable login evidence blocks dispatch. */ }
  throw new Error("Subscription-only policy: a supported subscription login could not be verified.");
}
