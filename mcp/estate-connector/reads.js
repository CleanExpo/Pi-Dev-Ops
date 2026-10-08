import { z } from "zod";
import {
  allowedRepos, isPidevopsProject, isUniteProject, loadRegistry, UNITE_SURFACES,
} from "./registry.js";
import { githubStatus, linearReady, missionControlLive, piceoHealth, probeUrls } from "./upstream.js";
import { fail, ok, queueCounts } from "./shape.js";

const READ = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true };
const LOCAL = { ...READ, openWorldHint: false };
const probeArg = { probe: z.boolean().optional().describe("When true, request each recorded https URL and return the status code.") };
const repoArg = { repo: z.string().optional().describe("owner/name. Must already be in the project register.") };
const limitArg = { limit: z.number().int().min(1).max(50).optional().describe("How many rows to return. Default 20.") };

function registry(ctx) {
  return loadRegistry(ctx.config.projectsPath);
}

function deployments(projects) {
  const rows = [];
  for (const project of projects) {
    for (const [kind, url] of Object.entries(project.deployments || {})) {
      rows.push({ project_id: project.id, repo: project.repo, kind, url });
    }
  }
  return rows;
}

async function deploymentView(ctx, projects, probe) {
  const rows = deployments(projects);
  if (!probe) return { deployments: rows, probed: false };
  const result = await probeUrls(ctx.fetchImpl, rows);
  return { deployments: result.checked, probed: true, truncated: result.truncated };
}

function checkRepo(projects, repo) {
  if (!allowedRepos(projects).has(String(repo).toLowerCase())) return "repo is not in the project register";
  return null;
}

export function registerReadTools(server, ctx) {
  server.registerTool("unite_status", {
    title: "Unite-Group status",
    description: "Read Unite-Group repo status, the older MCP apps this connector does not replace, and how many shared queue items are tagged unite.",
    inputSchema: repoArg,
    annotations: READ,
  }, async ({ repo }) => {
    const { projects, error } = registry(ctx);
    const name = repo || "CleanExpo/Unite-Group";
    const problem = checkRepo(projects, name);
    if (problem) return fail(problem);
    const items = await ctx.store.listQueue("unite");
    return ok({
      register_error: error,
      surfaces: UNITE_SURFACES.filter((surface) => surface.repo === "CleanExpo/Unite-Group"),
      github: await githubStatus(ctx.config, ctx.fetchImpl, name),
      coordination_queue: queueCounts(items),
    });
  });

  server.registerTool("unite_health", {
    title: "Unite-Group health",
    description: "Read whether the GitHub token is set and whether the Unite-Group repo answered. Does not spend money.",
    inputSchema: repoArg,
    annotations: READ,
  }, async ({ repo }) => {
    const { projects } = registry(ctx);
    const name = repo || "CleanExpo/Unite-Group";
    const problem = checkRepo(projects, name);
    if (problem) return fail(problem);
    return ok({ github_token_configured: Boolean(ctx.config.githubToken), github: await githubStatus(ctx.config, ctx.fetchImpl, name) });
  });

  server.registerTool("unite_projects", {
    title: "Unite-Group projects",
    description: "Read Unite-Group rows from the Pi-Dev-Ops project register.",
    inputSchema: {},
    annotations: LOCAL,
  }, async () => {
    const loaded = registry(ctx);
    return ok({ error: loaded.error, projects: loaded.projects.filter(isUniteProject) });
  });

  server.registerTool("unite_queue", {
    title: "Unite-Group queue",
    description: "Read shared queue items tagged unite, plus Linear issues in Ready for Pi-Dev for the Unite project when LINEAR_API_KEY is set.",
    inputSchema: {},
    annotations: READ,
  }, async () => {
    const { projects, error } = registry(ctx);
    const unite = projects.filter(isUniteProject);
    const items = await ctx.store.listQueue("unite");
    const linear = await linearReady(ctx.config, ctx.fetchImpl, unite.map((project) => project.linear_project_id));
    return ok({ register_error: error, coordination: items, linear });
  });

  server.registerTool("unite_deployments", {
    title: "Unite-Group deployments",
    description: "Read the https URLs recorded for Unite-Group. Set probe true to request each URL.",
    inputSchema: probeArg,
    annotations: READ,
  }, async ({ probe }) => ok(await deploymentView(ctx, registry(ctx).projects.filter(isUniteProject), probe)));

  server.registerTool("pidevops_status", {
    title: "Pi-Dev-Ops status",
    description: "Read a short Pi-Dev-Ops picture: /health, shared queue counts, and recorded deployment URLs.",
    inputSchema: {},
    annotations: READ,
  }, async () => {
    const projects = registry(ctx).projects.filter(isPidevopsProject);
    const items = await ctx.store.listQueue("pidevops");
    return ok({
      health: await piceoHealth(ctx.config, ctx.fetchImpl),
      coordination_queue: queueCounts(items),
      deployments: deployments(projects),
    });
  });

  server.registerTool("pidevops_health", {
    title: "Pi-Dev-Ops health",
    description: "Read Pi-CEO /health. The detailed payload is returned only when PICEO_BEARER is set. Booleans only for credential presence.",
    inputSchema: {},
    annotations: READ,
  }, async () => ok(await piceoHealth(ctx.config, ctx.fetchImpl)));

  server.registerTool("pidevops_projects", {
    title: "Pi-Dev-Ops projects",
    description: "Read the Pi-Dev-Ops and Margot rows from the project register.",
    inputSchema: {},
    annotations: LOCAL,
  }, async () => {
    const loaded = registry(ctx);
    return ok({ error: loaded.error, projects: loaded.projects.filter(isPidevopsProject) });
  });

  server.registerTool("pidevops_queue", {
    title: "Pi-Dev-Ops queue",
    description: "Read shared queue items tagged pidevops, plus Linear Ready for Pi-Dev issues on the Pi-Dev-Ops and Margot projects.",
    inputSchema: {},
    annotations: READ,
  }, async () => {
    const projects = registry(ctx).projects.filter(isPidevopsProject);
    const items = await ctx.store.listQueue("pidevops");
    const linear = await linearReady(ctx.config, ctx.fetchImpl, projects.map((project) => project.linear_project_id));
    return ok({ coordination: items, linear });
  });

  server.registerTool("pidevops_deployments", {
    title: "Pi-Dev-Ops deployments",
    description: "Read the https URLs recorded for Pi-Dev-Ops and Margot. Set probe true to request each URL.",
    inputSchema: probeArg,
    annotations: READ,
  }, async ({ probe }) => ok(await deploymentView(ctx, registry(ctx).projects.filter(isPidevopsProject), probe)));

  server.registerTool("mc_status", {
    title: "Mission Control status",
    description: "Read the shared coordination picture: recent notes, queue counts, and the Mission Control live route when it answers.",
    inputSchema: {},
    annotations: READ,
  }, async () => {
    const items = await ctx.store.listQueue();
    const activity = await ctx.store.listActivity(5);
    return ok({
      coordination_queue: queueCounts(items),
      recent_activity: activity,
      live: await missionControlLive(ctx.config, ctx.fetchImpl),
    });
  });

  server.registerTool("mc_health", {
    title: "Mission Control health",
    description: "Read Pi-CEO /health and whether /api/mission-control/live answered. A 401 on the live route means the dashboard session is missing, not that the connector is down.",
    inputSchema: {},
    annotations: READ,
  }, async () => ok({
    service: await piceoHealth(ctx.config, ctx.fetchImpl),
    live: await missionControlLive(ctx.config, ctx.fetchImpl),
  }));

  server.registerTool("mc_projects", {
    title: "Mission Control projects",
    description: "Read every project the Mission Control poller is allowed to claim, from the project register.",
    inputSchema: {},
    annotations: LOCAL,
  }, async () => {
    const loaded = registry(ctx);
    return ok({ error: loaded.error, projects: loaded.projects });
  });

  server.registerTool("mc_queue", {
    title: "Mission Control queue",
    description: "Read the shared coordination queue and the Linear Ready for Pi-Dev issues Mission Control shows, across the registered projects.",
    inputSchema: {},
    annotations: READ,
  }, async () => {
    const { projects, error } = registry(ctx);
    const coordination = await ctx.store.listQueue();
    const linear = await linearReady(ctx.config, ctx.fetchImpl, projects.map((project) => project.linear_project_id));
    return ok({ register_error: error, coordination, linear });
  });

  server.registerTool("coord_list_activity", {
    title: "List coordination activity",
    description: "Read the shared feed of notes, queue updates, claims, and releases so bots can see each other's work.",
    inputSchema: limitArg,
    annotations: LOCAL,
  }, async ({ limit }) => ok({ activity: await ctx.store.listActivity(limit || 20) }));

  server.registerTool("coord_list_audit", {
    title: "List write audit",
    description: "Read the audit log of write attempts: who, which tool, when, and whether it was accepted.",
    inputSchema: limitArg,
    annotations: LOCAL,
  }, async ({ limit }) => ok({ audit: await ctx.store.listAudit(limit || 20) }));
}
