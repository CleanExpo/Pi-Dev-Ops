import { z } from "zod";
import { loadProjects, projectById } from "../../lib/projects.js";
import { fetchJson, joinUrl } from "../../lib/upstream.js";
import { addNote } from "../../lib/notes.js";
import { auditedWrite } from "../../lib/writes.js";
import { ok } from "../../lib/results.js";
import { botField } from "../../lib/schemas.js";

export const pidevops = {
  id: "pidevops",
  title: "Pi-Dev-Ops",
  tools() {
    return [healthTool(), projectsTool(), deploymentsTool(), statusTool()];
  },
};

function healthTool() {
  return {
    name: "pidevops_health",
    title: "Pi-Dev-Ops health",
    description: "[READ] Live /health from the Pi-Dev-Ops backend when PICEO_BASE_URL is set.",
    readOnly: true,
    inputSchema: {},
    async handler(_args, ctx) {
      const base = ctx.env.PICEO_BASE_URL;
      if (!base) return ok({ configured: false, reason: "Set PICEO_BASE_URL to read live Pi-Dev-Ops health." });
      return ok(await fetchJson(joinUrl(base, "/health"), ctx.env.PICEO_BEARER_TOKEN));
    },
  };
}

function projectsTool() {
  return {
    name: "pidevops_projects",
    title: "Project list",
    description: "[READ] Projects from config/harness/projects.json: id, repo, name, team, and deployment addresses.",
    readOnly: true,
    inputSchema: {
      id: z.string().optional().describe("Return one project id, for example pi-dev-ops."),
    },
    async handler(args, ctx) {
      if (!args.id) return ok(loadProjects(ctx.repoRoot));
      const found = projectById(ctx.repoRoot, args.id);
      return ok({ ok: found.ok, project: found.project });
    },
  };
}

function deploymentsTool() {
  return {
    name: "pidevops_deployments",
    title: "Deployment addresses",
    description: "[READ] Deployment addresses recorded in the project list. This does not deploy or change anything.",
    readOnly: true,
    inputSchema: {
      id: z.string().optional().describe("Limit to one project id."),
    },
    async handler(args, ctx) {
      const loaded = loadProjects(ctx.repoRoot);
      const rows = loaded.projects
        .filter((row) => !args.id || row.id === args.id)
        .map((row) => ({ id: row.id, repo: row.repo, deployments: row.deployments }));
      return ok({ ok: loaded.ok, count: rows.length, deployments: rows });
    },
  };
}

function statusTool() {
  return {
    name: "pidevops_post_status",
    title: "Post a Pi-Dev-Ops status",
    description: "[WRITE] Post a Pi-Dev-Ops status note on the shared feed. Audited. Does not deploy or merge.",
    readOnly: false,
    inputSchema: {
      text: z.string().describe("Status text, up to 2000 characters."),
      bot: botField,
    },
    handler(args, ctx) {
      return auditedWrite(ctx, "pidevops_post_status", args.bot, "status pidevops", (bot) =>
        addNote(ctx, bot, "pidevops", args.text));
    },
  };
}
