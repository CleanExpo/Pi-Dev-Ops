import fs from "node:fs";

/** Surfaces that already exist and are intentionally not this connector. */
export const UNITE_SURFACES = [
  {
    name: "pi-ceo-operator-mcp",
    repo: "CleanExpo/Unite-Group",
    path: "packages/pi-ceo-operator-mcp",
    transport: "local Skybridge app",
    serves: "read-only portfolio card for one operator session",
  },
  {
    name: "veritas-kanban-mcp",
    repo: "CleanExpo/Unite-Group",
    path: "apps/web/packages/veritas-kanban-mcp",
    transport: "stdio",
    serves: "a local kanban board, not Mission Control",
  },
  {
    name: "pi-ceo-server",
    repo: "CleanExpo/Pi-Dev-Ops",
    path: "mcp/pi-ceo-server.js",
    transport: "stdio",
    serves: "Claude Desktop on one machine, including tools this connector refuses",
  },
];

export function loadRegistry(filePath) {
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return { projects: [], error: "project register unreadable" };
  }
  const rows = Array.isArray(raw?.projects) ? raw.projects : [];
  const projects = rows
    .filter((row) => row && typeof row.id === "string" && typeof row.repo === "string")
    .map(compactProject);
  return { projects, error: null };
}

export function compactProject(row) {
  const deployments = {};
  const source = row.deployments && typeof row.deployments === "object" ? row.deployments : {};
  for (const [kind, url] of Object.entries(source)) {
    if (typeof url === "string" && url.startsWith("https://")) deployments[kind] = url;
  }
  return {
    id: row.id,
    repo: row.repo,
    linear_project_id: row.linear_project_id || null,
    linear_project_name: row.linear_project_name || null,
    linear_team_key: row.linear_team_key || null,
    deployments,
    scan_priority: row.scan_priority || null,
  };
}

export function isUniteProject(project) {
  return /unite/i.test(project.id) || /unite-group/i.test(project.repo || "");
}

export function isPidevopsProject(project) {
  return project.repo === "CleanExpo/Pi-Dev-Ops" || project.id === "pi-dev-ops" || project.id === "margot";
}

export function allowedRepos(projects) {
  const names = new Set(projects.map((project) => project.repo.toLowerCase()));
  names.add("cleanexpo/unite-group");
  names.add("cleanexpo/pi-dev-ops");
  return names;
}
