import fs from "node:fs";
import path from "node:path";

export function findRepoRoot(start) {
  let dir = start;
  for (let i = 0; i < 8; i += 1) {
    if (fs.existsSync(path.join(dir, "config", "harness", "projects.json"))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return start;
}

function publicProject(row) {
  return {
    id: row.id,
    repo: row.repo || null,
    name: row.linear_project_name || null,
    team: row.linear_team_key || null,
    deployments: row.deployments || {},
  };
}

export function loadProjects(repoRoot) {
  const file = path.join(repoRoot, "config", "harness", "projects.json");
  try {
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    const projects = Array.isArray(data.projects) ? data.projects.map(publicProject) : [];
    return { ok: true, projects };
  } catch {
    return { ok: false, projects: [], error: "project list file missing" };
  }
}

export function projectById(repoRoot, id) {
  const loaded = loadProjects(repoRoot);
  const project = loaded.projects.find((row) => row.id === id) || null;
  return { ...loaded, project };
}
