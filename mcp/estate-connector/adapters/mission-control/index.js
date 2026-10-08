import { z } from "zod";
import { fetchJson, joinUrl } from "../../lib/upstream.js";
import { addNote } from "../../lib/notes.js";
import { claimItem, listQueue, releaseItem, upsertItem } from "../../lib/queue.js";
import { auditedWrite } from "../../lib/writes.js";
import { ok } from "../../lib/results.js";
import { botField, systemField } from "../../lib/schemas.js";

export const missionControl = {
  id: "mc",
  title: "Mission Control",
  tools() {
    return [liveTool(), queueTool(), noteTool(), updateTool(), claimTool(), releaseTool()];
  },
};

function liveTool() {
  return {
    name: "mc_live",
    title: "Mission Control live",
    description: "[READ] Mission Control live page: sessions, queue snapshot, and health. Needs PICEO_BASE_URL.",
    readOnly: true,
    inputSchema: {},
    async handler(_args, ctx) {
      const coordination_queue = await listQueue(ctx);
      const base = ctx.env.PICEO_BASE_URL;
      if (!base) {
        return ok({
          configured: false,
          reason: "Set PICEO_BASE_URL to read live Mission Control. The shared queue is still included.",
          coordination_queue,
        });
      }
      const live = await fetchJson(joinUrl(base, "/api/mission-control/live"), ctx.env.PICEO_BEARER_TOKEN);
      return ok({ ...live, coordination_queue });
    },
  };
}

function queueTool() {
  return {
    name: "mc_queue",
    title: "Shared queue",
    description: "[READ] Queue items the bots share. This is the coordination queue, not a delete list.",
    readOnly: true,
    inputSchema: { system: systemField },
    async handler(args, ctx) {
      return ok(await listQueue(ctx, args.system));
    },
  };
}

function noteTool() {
  return {
    name: "mc_post_note",
    title: "Post a Mission Control note",
    description: "[WRITE] Add a Mission Control note on the shared feed. Audited.",
    readOnly: false,
    inputSchema: {
      text: z.string().describe("Note text, up to 2000 characters."),
      bot: botField,
    },
    handler(args, ctx) {
      return auditedWrite(ctx, "mc_post_note", args.bot, "note mc", (bot) => addNote(ctx, bot, "mc", args.text));
    },
  };
}

function updateTool() {
  return {
    name: "mc_update_queue_item",
    title: "Update a queue item",
    description: "[WRITE] Create or update a shared queue item. Audited. Cannot delete. Use claim to take an item.",
    readOnly: false,
    inputSchema: {
      id: z.string().describe("Item id. Letters, numbers, and . _ : -"),
      title: z.string().optional().describe("Required when creating. Up to 200 characters."),
      note: z.string().optional().describe("Note, up to 2000 characters."),
      status: z.enum(["open", "blocked", "done"]).optional(),
      system: systemField,
      bot: botField,
    },
    handler(args, ctx) {
      return auditedWrite(ctx, "mc_update_queue_item", args.bot, `update ${args.id}`, (bot) =>
        upsertItem(ctx, bot, args));
    },
  };
}

function claimTool() {
  return {
    name: "mc_claim_work",
    title: "Claim queue work",
    description: "[WRITE] Claim an existing queue item so other bots can see who has it. Audited.",
    readOnly: false,
    inputSchema: {
      id: z.string().describe("Item id to claim."),
      bot: botField,
    },
    handler(args, ctx) {
      return auditedWrite(ctx, "mc_claim_work", args.bot, `claim ${args.id}`, (bot) => claimItem(ctx, bot, args.id));
    },
  };
}

function releaseTool() {
  return {
    name: "mc_release_work",
    title: "Release queue work",
    description: "[WRITE] Release an item you claimed, back to open. Audited. Does not delete it.",
    readOnly: false,
    inputSchema: {
      id: z.string().describe("Item id to release."),
      bot: botField,
    },
    handler(args, ctx) {
      return auditedWrite(ctx, "mc_release_work", args.bot, `release ${args.id}`, (bot) =>
        releaseItem(ctx, bot, args.id));
    },
  };
}
