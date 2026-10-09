import { z } from "zod";
import { addNote, listNotes } from "../../lib/notes.js";
import { auditedWrite } from "../../lib/writes.js";
import { ok } from "../../lib/results.js";
import { botField, systemField } from "../../lib/schemas.js";

/** Shared feed every bot can read. Not a product project. */
export const coord = {
  id: "coord",
  title: "Shared coordination",
  tools() {
    return [activityTool(), postTool()];
  },
};

function activityTool() {
  return {
    name: "coord_activity",
    title: "Shared activity",
    description: "[READ] Recent notes from every bot on the shared feed.",
    readOnly: true,
    inputSchema: {
      system: systemField,
      limit: z.number().int().min(1).max(100).optional().describe("How many notes. Default 30."),
    },
    async handler(args, ctx) {
      return ok(await listNotes(ctx, args));
    },
  };
}

function postTool() {
  return {
    name: "coord_post_note",
    title: "Post a shared note",
    description: "[WRITE] Add a note to the shared feed. Audited. Pick a system tag so other bots can filter it.",
    readOnly: false,
    inputSchema: {
      text: z.string().describe("Note text, up to 2000 characters."),
      system: z.string().describe("System id: coord, pidevops, unite, mc, restoreassist, synthex, or drnrpg."),
      bot: botField,
    },
    handler(args, ctx) {
      const system = args.system || "coord";
      return auditedWrite(ctx, "coord_post_note", args.bot, `note ${system}`, (bot) =>
        addNote(ctx, bot, system, args.text));
    },
  };
}
