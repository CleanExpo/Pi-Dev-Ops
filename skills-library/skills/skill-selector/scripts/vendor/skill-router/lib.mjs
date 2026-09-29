// Shared indexing/search logic for the skill library, used by both the MCP
// server (server.mjs) and the maintenance script (audit.mjs). Split out so
// audit.mjs can import it without triggering server.mjs's stdio transport
// side effect.
import { readFile, readdir, realpath, stat } from "node:fs/promises";
import path from "node:path";

export const HOME = process.env.HOME ?? "/root";
export const ROOTS = [
  { dir: path.join(HOME, ".claude/skills"), source: "active" },
  { dir: path.join(HOME, ".claude/plugins"), source: "plugin" },
  { dir: path.join(HOME, ".claude/skill-vault"), source: "vault" },
];
export const SOURCE_RANK = { active: 0, plugin: 1, vault: 2 };
export const BODY_SCORE_CHARS = 8000;

export function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function tokens(text) {
  return new Set((text.match(/\w+/g) ?? []).map((t) => t.toLowerCase()));
}

// Filler words weak/terse callers pad queries with ("make my website load
// faster"). Filtered from the QUERY only — never the haystack — so they can't
// outvote the domain terms. If the whole query is filler, fall back unfiltered.
const STOPWORDS = new Set([
  "the", "a", "an", "my", "me", "i", "you", "your", "to", "for", "of", "in",
  "on", "with", "and", "or", "is", "are", "it", "this", "that", "how", "do",
  "does", "can", "want", "need", "help", "please", "make", "get", "set", "up",
  "use", "using", "when", "what", "which", "some", "more", "so", "at", "be",
]);
export function queryTokens(text) {
  const all = tokens(text);
  const filtered = new Set([...all].filter((t) => !STOPWORDS.has(t) && t.length > 1));
  return filtered.size > 0 ? filtered : all;
}

// Parses `key: value` out of a `---\n...\n---` frontmatter block, including
// YAML block scalars (`description: >-` + indented lines — 44 of the ~185
// real skills use that form). Tolerant of missing frontmatter or keys.
export function parseFrontmatter(raw) {
  const out = {};
  if (!raw.startsWith("---")) return out;
  const end = raw.indexOf("\n---", 3);
  if (end === -1) return out;
  const lines = raw.slice(3, end).split("\n");
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(name|description):\s*(.*)$/);
    if (!m) continue;
    let val = m[2].trim();
    if (/^[>|][0-9+-]{0,2}$/.test(val)) {
      const parts = [];
      // blank lines inside a block scalar are paragraph breaks, not the end
      while (i + 1 < lines.length && (/^\s+\S/.test(lines[i + 1]) || lines[i + 1].trim() === "")) {
        const next = lines[++i].trim();
        if (next) parts.push(next);
      }
      val = parts.join(" ");
    }
    out[m[1]] = val.replace(/^["']|["']$/g, "");
  }
  return out;
}

export function fallbackDescription(body) {
  for (const line of body.split("\n")) {
    const t = line.trim();
    if (t && !t.startsWith("#")) return t.slice(0, 300);
  }
  return "";
}

// Most of ~/.claude/skills is symlinks into a shared store (../../.agents/skills/*),
// and Dirent.isDirectory() doesn't follow symlinks -- so a plain readdir walk
// silently misses most skills. Resolve symlinked dirs via stat, and track
// real paths already visited to survive a symlink cycle.
export async function findSkillFiles(dir, exclude, seen = new Set()) {
  const results = [];
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return results; // missing/unreadable root: tolerate silently
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (exclude && exclude(full)) continue;
    let isDir = entry.isDirectory();
    if (!isDir && entry.isSymbolicLink()) {
      try {
        const real = await realpath(full);
        if (seen.has(real)) continue;
        if ((await stat(full)).isDirectory()) {
          seen.add(real);
          isDir = true;
        }
      } catch {
        continue; // broken symlink
      }
    }
    if (isDir) {
      results.push(...(await findSkillFiles(full, exclude, seen)));
    } else if (entry.name === "SKILL.md") {
      results.push(full);
    }
  }
  return results;
}

export function isExcludedPluginPath(p) {
  return p.includes("/plugins/cache/") || p.includes("/plugins/marketplaces/");
}

export async function loadSkill(filePath, source) {
  let raw;
  try {
    raw = await readFile(filePath, "utf8");
  } catch {
    return null;
  }
  const fm = parseFrontmatter(raw);
  const bodyStart = raw.startsWith("---") ? raw.indexOf("\n---", 3) + 4 : 0;
  const body = raw.slice(Math.max(bodyStart, 0));
  const name = fm.name || path.basename(path.dirname(filePath));
  const description = fm.description || fallbackDescription(body);
  return {
    id: slugify(name),
    name,
    description,
    source,
    path: filePath,
    bodyForScoring: body.slice(0, BODY_SCORE_CHARS),
  };
}

let index = new Map(); // id -> skill item (winner), with shadowedBy: string[]

export function getIndex() {
  return index;
}

export async function buildIndex() {
  const counts = { active: 0, plugin: 0, vault: 0, shadowed: 0 };
  const byId = new Map();
  for (const { dir, source } of ROOTS) {
    const exclude = source === "plugin" ? isExcludedPluginPath : undefined;
    const files = await findSkillFiles(dir, exclude);
    for (const file of files) {
      const item = await loadSkill(file, source);
      if (!item) continue;
      counts[source]++;
      const existing = byId.get(item.id);
      if (!existing) {
        item.shadowedBy = [];
        byId.set(item.id, item);
        continue;
      }
      // keep the higher-precedence entry (active > plugin > vault)
      const existingWins = SOURCE_RANK[existing.source] <= SOURCE_RANK[item.source];
      const winner = existingWins ? existing : item;
      const loser = existingWins ? item : existing;
      winner.shadowedBy = [...(existing.shadowedBy ?? []), loser.path].filter(
        (p, i, arr) => arr.indexOf(p) === i,
      );
      counts.shadowed++;
      byId.set(item.id, winner);
    }
  }
  index = byId;
  return counts;
}

export function scoreItem(item, qTokens, queryText) {
  const haystackText = [item.name, item.description, item.bodyForScoring]
    .join("\n")
    .toLowerCase();
  const haystackTokens = tokens(haystackText);
  let overlap = 0;
  for (const t of qTokens) if (haystackTokens.has(t)) overlap++;
  let score = overlap;
  if (queryText && haystackText.includes(queryText)) score += 5;
  const nameLower = item.name.toLowerCase();
  const descLower = item.description.toLowerCase();
  const nameFragments = nameLower.split(/[^a-z0-9]+/).filter((n) => n.length >= 3);
  for (const t of qTokens) {
    if (nameLower.includes(t)) score += 3;
    // partial name credit: query "website" should still hit the name "web-perf"
    else if (nameFragments.some((n) => t.includes(n))) score += 2;
    if (descLower.includes(t)) score += 1.5;
  }
  if (score === 0) return 0;
  return score + 1 / Math.sqrt(Math.max(haystackTokens.size, 1));
}

export function search(query, limit) {
  const queryText = query.toLowerCase().trim();
  const qTokens = queryTokens(queryText);
  const results = [];
  for (const item of index.values()) {
    const score = scoreItem(item, qTokens, queryText);
    if (score > 0) {
      results.push({
        id: item.id,
        name: item.name,
        description: item.description,
        source: item.source,
        path: item.path,
        score,
      });
    }
  }
  results.sort((a, b) => b.score - a.score);
  return results.slice(0, limit);
}

export function closestIds(query, n) {
  const qTokens = queryTokens(query.toLowerCase());
  const scored = [...index.values()].map((item) => ({
    id: item.id,
    score: scoreItem(item, qTokens, query.toLowerCase()),
  }));
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, n).map((s) => s.id);
}
