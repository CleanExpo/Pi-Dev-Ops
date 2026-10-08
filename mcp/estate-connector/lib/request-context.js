import { AsyncLocalStorage } from "node:async_hooks";
import { normalizeBot } from "./bots.js";

const storage = new AsyncLocalStorage();

export function runWithBot(bot, fn) {
  return storage.run({ bot: normalizeBot(bot) }, fn);
}

export function currentBot() {
  return storage.getStore()?.bot || "";
}

/** Header wins. A different bot in the URL is a mismatch. */
export function botsFromRequest(headerValue, queryValue) {
  const header = normalizeBot(headerValue);
  const query = normalizeBot(typeof queryValue === "string" ? queryValue : "");
  if (header && query && header !== query) {
    return { mismatch: true, bot: "" };
  }
  return { mismatch: false, bot: header || query };
}
