import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseBots } from "./bots.js";
import { createAudit } from "./audit.js";
import { createStore } from "./store.js";
import { findRepoRoot } from "./projects.js";
import { adapters } from "../adapters/registry.js";

export function createContext(opts) {
  const env = opts.env || {};
  const here = path.dirname(fileURLToPath(import.meta.url));
  const repoRoot = opts.repoRoot || env.ESTATE_MCP_REPO_ROOT || findRepoRoot(path.resolve(here, ".."));
  const dataDir = opts.dataDir || env.ESTATE_MCP_DATA_DIR || path.join(repoRoot, "mcp", "estate-connector", "data");
  return {
    repoRoot,
    dataDir,
    store: createStore(dataDir),
    audit: createAudit(dataDir),
    bots: parseBots(opts.bots ?? env.ESTATE_MCP_BOTS),
    env,
    systems: new Set(adapters.map((adapter) => adapter.id)),
  };
}
