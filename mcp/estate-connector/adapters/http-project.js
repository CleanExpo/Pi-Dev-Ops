import { z } from "zod";
import { projectById } from "../lib/projects.js";
import { fetchJson, joinUrl } from "../lib/upstream.js";
import { addNote } from "../lib/notes.js";
import { auditedWrite } from "../lib/writes.js";
import { ok } from "../lib/results.js";
import { botField } from "../lib/schemas.js";

/**
 * Shared shape for a project that is mostly "read a site, post a note".
 * A new project folder calls this and is added in adapters/registry.js.
 */
export function httpProjectAdapter(config) {
  return {
    id: config.id,
    title: config.title,
    tools() {
      return [statusTool(config), projectsTool(config), noteTool(config)];
    },
  };
}

/** Health read plus a shared-board note. Base URL falls back to defaultBase. */
export function healthNoteAdapter(config) {
  return {
    id: config.id,
    title: config.title,
    tools() {
      return [healthTool(config), noteTool({ ...config, prefix: config.prefix || config.id })];
    },
  };
}

function statusTool(config) {
  return {
    name: `${config.prefix}_status`,
    title: `${config.title} status`,
    description: `[READ] Live status for ${config.title} when ${config.baseEnv} is set. Otherwise the project-list row only.`,
    readOnly: true,
    inputSchema: {},
    async handler(_args, ctx) {
      const registry = projectById(ctx.repoRoot, config.registryId).project;
      const base = ctx.env[config.baseEnv];
      if (!base) {
        return ok({
          configured: false,
          reason: `Set ${config.baseEnv} to read the live ${config.title} site.`,
          registry,
        });
      }
      const statusPath = ctx.env[config.statusPathEnv] || config.statusPathDefault;
      const live = await fetchJson(joinUrl(base, statusPath), ctx.env[config.tokenEnv]);
      return ok({ ...live, registry });
    },
  };
}

function healthTool(config) {
  const prefix = config.prefix || config.id;
  return {
    name: `${prefix}_health`,
    title: `${config.title} health`,
    description: `[READ] Live health for ${config.title}. ${config.baseEnv} overrides the default site. A bearer token is sent only when ${config.tokenEnv} is set.`,
    readOnly: true,
    inputSchema: {},
    async handler(_args, ctx) {
      const registry = projectById(ctx.repoRoot, config.registryId).project;
      const base = ctx.env[config.baseEnv] || config.defaultBase;
      const live = await fetchJson(joinUrl(base, "/api/health"), ctx.env[config.tokenEnv]);
      return ok({ ...live, registry });
    },
  };
}

function projectsTool(config) {
  return {
    name: `${config.prefix}_projects`,
    title: `${config.title} projects`,
    description: `[READ] Project rows for ${config.title}. Uses ${config.projectsPathEnv} when that path is set.`,
    readOnly: true,
    inputSchema: {},
    async handler(_args, ctx) {
      const registry = projectById(ctx.repoRoot, config.registryId).project;
      const base = ctx.env[config.baseEnv];
      const projectsPath = ctx.env[config.projectsPathEnv];
      if (!base || !projectsPath) {
        return ok({
          configured: false,
          reason: `Set ${config.baseEnv} and ${config.projectsPathEnv} to read a live project list.`,
          registry,
        });
      }
      const live = await fetchJson(joinUrl(base, projectsPath), ctx.env[config.tokenEnv]);
      return ok({ ...live, registry });
    },
  };
}

function noteTool(config) {
  const name = `${config.prefix}_post_note`;
  return {
    name,
    title: `Post a ${config.title} note`,
    description: `[WRITE] Add a note tagged ${config.id} on the shared feed. Audited. Does not change the live site.`,
    readOnly: false,
    inputSchema: {
      text: z.string().describe("Note text, up to 2000 characters."),
      bot: botField,
    },
    handler(args, ctx) {
      const summary = `note ${config.id}`;
      return auditedWrite(ctx, name, args.bot, summary, (bot) => addNote(ctx, bot, config.id, args.text));
    },
  };
}
