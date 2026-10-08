import { z } from "zod";
import { actorProblem } from "./context.js";
import { fail, ok, scrubText } from "./shape.js";

const WRITE = { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false };

const actor = z.string().min(1).max(64).regex(/^[A-Za-z][A-Za-z0-9 ._-]{0,63}$/).describe("Who is acting. Example: Queue, Scout, Margot, Projects Manager.");
const itemId = z.string().min(1).max(80).regex(/^[a-z0-9][a-z0-9_.:-]{0,79}$/).describe("Stable id, lowercase. Example: gate-check.");
const system = z.enum(["unite", "pidevops", "mc"]).describe("Which system this item belongs to.");
const status = z.enum(["open", "claimed", "blocked", "done"]).describe("Coordination status. This does not close a Linear issue.");

async function audited(ctx, actorName, tool, summary, fn) {
  const problem = actorProblem(ctx.config, actorName);
  if (problem) {
    await ctx.store.addAudit({ actor: actorName, tool, ok: false, summary: problem });
    return fail(problem);
  }
  const result = await fn();
  await ctx.store.addAudit({
    actor: actorName,
    tool,
    ok: Boolean(result.ok),
    summary: result.ok ? summary : result.error,
    ref: result.item?.id || result.activity?.id || null,
  });
  if (!result.ok) return fail(result.error);
  return ok({ ...result, write: true, audit: true });
}

export function registerWriteTools(server, ctx) {
  server.registerTool("coord_post_note", {
    title: "WRITE — post a coordination note",
    description: "WRITE. Add a note to the shared feed every bot can read. Does not change Linear, GitHub, or production data. The call is audit-logged.",
    inputSchema: {
      actor,
      system: z.enum(["unite", "pidevops", "mc", "coord"]),
      text: z.string().min(1).max(2000).describe("The note. Tokens pasted here are scrubbed."),
    },
    annotations: WRITE,
  }, async ({ actor: actorName, system: noteSystem, text }) => audited(ctx, actorName, "coord_post_note", "note posted", async () => {
    const activity = await ctx.store.addActivity({
      actor: actorName,
      system: noteSystem,
      kind: "note",
      summary: scrubText(text),
      ref: null,
    });
    return { ok: true, activity };
  }));

  server.registerTool("mc_update_queue_item", {
    title: "WRITE — add or update a queue item",
    description: "WRITE. Add or update a shared coordination queue item. Does not edit Linear, delete anything, or deploy. Claim and release are separate tools. The call is audit-logged.",
    inputSchema: {
      actor,
      id: itemId,
      title: z.string().min(1).max(200).optional().describe("Required when the id is new."),
      system: system.optional(),
      status: status.optional(),
      note: z.string().max(2000).optional(),
    },
    annotations: WRITE,
  }, async ({ actor: actorName, id, title, system: itemSystem, status: itemStatus, note }) => audited(
    ctx, actorName, "mc_update_queue_item", "queue item saved", async () => {
      if (itemStatus === "claimed") return { ok: false, error: "use mc_claim_work to claim" };
      const saved = await ctx.store.upsert({
        id,
        actor: actorName,
        title,
        system: itemSystem,
        status: itemStatus,
        note: note === undefined ? undefined : scrubText(note),
      });
      if (!saved.ok) return saved;
      const activity = await ctx.store.addActivity({
        actor: actorName,
        system: saved.item.system,
        kind: "queue_update",
        summary: `${saved.created ? "added" : "updated"} ${saved.item.id}: ${saved.item.status}`,
        ref: saved.item.id,
      });
      return { ok: true, created: saved.created, item: saved.item, activity };
    },
  ));

  server.registerTool("mc_claim_work", {
    title: "WRITE — claim work",
    description: "WRITE. Claim a shared queue item when it is free or already yours. Refuses to take an item another bot holds. Does not change Linear. The call is audit-logged.",
    inputSchema: { actor, id: itemId },
    annotations: WRITE,
  }, async ({ actor: actorName, id }) => audited(ctx, actorName, "mc_claim_work", "work claimed", async () => {
    const claimed = await ctx.store.claim(id, actorName);
    if (!claimed.ok) return claimed;
    const activity = await ctx.store.addActivity({
      actor: actorName,
      system: claimed.item.system,
      kind: "claim",
      summary: `${actorName} claimed ${id}`,
      ref: id,
    });
    return { ok: true, item: claimed.item, activity };
  }));

  server.registerTool("mc_release_work", {
    title: "WRITE — release work",
    description: "WRITE. Release a shared queue item you currently hold. Sets it back to open. Does not delete the item or change Linear. The call is audit-logged.",
    inputSchema: { actor, id: itemId },
    annotations: WRITE,
  }, async ({ actor: actorName, id }) => audited(ctx, actorName, "mc_release_work", "work released", async () => {
    const released = await ctx.store.release(id, actorName);
    if (!released.ok) return released;
    const activity = await ctx.store.addActivity({
      actor: actorName,
      system: released.item.system,
      kind: "release",
      summary: `${actorName} released ${id}`,
      ref: id,
    });
    return { ok: true, item: released.item, activity };
  }));
}
