import { AsyncLocalStorage } from "node:async_hooks";

export const requestAls = new AsyncLocalStorage();

export function currentBotName() {
  return requestAls.getStore()?.botName || "";
}

const ACTOR = /^[A-Za-z][A-Za-z0-9 ._-]{0,63}$/;

export function actorProblem(config, actor) {
  const header = currentBotName();
  if (header && header !== actor) return "X-Bot-Name does not match actor";
  if (config.actors && !config.actors.includes(actor)) return "actor is not in ESTATE_MCP_ACTORS";
  return null;
}

export function validActorShape(actor) {
  return ACTOR.test(actor);
}
