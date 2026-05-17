/** Convert a free-text title into a filename-safe slug. */
export function slugify(name: string): string {
  if (!name || !name.trim()) return "meeting";
  const ascii = name.normalize("NFKD").replace(/\p{M}/gu, "");
  const slug = ascii
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return (slug || "meeting").slice(0, 60).replace(/-+$/, "");
}
