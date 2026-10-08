/** Default bots that may call write tools. Capitals and extra spaces do not matter. */
const DEFAULT_BOTS = [
  "queue",
  "scout",
  "sentinel",
  "critic",
  "margot",
  "projects manager",
];

export function normalizeBot(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ");
}

/** @param {string | undefined} raw Comma-separated override. Empty uses the default list. */
export function parseBots(raw) {
  const source = raw && raw.trim() ? raw.split(",") : DEFAULT_BOTS;
  const names = source.map((item) => normalizeBot(item)).filter(Boolean);
  return new Set(names);
}
