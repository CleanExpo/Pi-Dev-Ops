import path from "node:path";
import { fileURLToPath } from "node:url";
import { configuredToken } from "./auth.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_PROJECTS = path.resolve(HERE, "../../config/harness/projects.json");
export const DEFAULT_BASE_URL = "https://pi-dev-ops-production.up.railway.app";

export function configFromEnv(env) {
  const base = safeBase(env.PICEO_BASE_URL || DEFAULT_BASE_URL);
  const actors = String(env.ESTATE_MCP_ACTORS || "")
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
  return {
    token: configuredToken(env.ESTATE_MCP_TOKEN),
    stateDir: env.ESTATE_MCP_STATE_DIR || path.resolve(HERE, "../../.harness/estate-mcp"),
    projectsPath: env.ESTATE_PROJECTS_PATH || DEFAULT_PROJECTS,
    piceoBaseUrl: base.url,
    piceoBaseUrlError: base.error,
    piceoBearer: String(env.PICEO_BEARER || "").trim(),
    githubToken: String(env.GITHUB_TOKEN || "").trim(),
    linearKey: String(env.LINEAR_API_KEY || "").trim(),
    actors: actors.length ? actors : null,
    port: Number(env.PORT || 8787),
    host: env.HOST || "0.0.0.0",
  };
}

function safeBase(raw) {
  const value = String(raw || "").trim().replace(/\/$/, "");
  let url;
  try {
    url = new URL(value);
  } catch {
    return { url: null, error: "PICEO_BASE_URL is not a URL" };
  }
  const local = url.hostname === "localhost" || url.hostname === "127.0.0.1";
  if (url.protocol !== "https:" && !(url.protocol === "http:" && local)) {
    return { url: null, error: "PICEO_BASE_URL must be https" };
  }
  if (url.username || url.password) return { url: null, error: "PICEO_BASE_URL must not include a password" };
  return { url: url.origin, error: null };
}
