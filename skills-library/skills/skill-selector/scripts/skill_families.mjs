#!/usr/bin/env node
// Family report: which skills share a name stem, and which entry point heads each family.
// Read-only. A family with no router head is where one word returns five siblings and the
// person gets a sub-skill instead of the entry point. Retiring or merging is a human call;
// this only measures.
//
//   node skill_families.mjs [--min 3] [--json]
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const HOME = process.env.HOME ?? os.homedir();
const ACTIVE = path.join(HOME, ".claude/skills");
const ROUTER = path.join(ACTIVE, "index.md");
const NAME_RE = /`([a-z0-9][a-z0-9:_-]*)`/g;

const args = process.argv.slice(2);
const mi = args.indexOf("--min");
const min = Math.max(Number(mi >= 0 ? args[mi + 1] : 3) || 3, 2);
const json = args.includes("--json");

let routerText = "";
try {
  routerText = fs.readFileSync(ROUTER, "utf8");
} catch {
  routerText = "";
}
const routed = new Set([...routerText.matchAll(NAME_RE)].map((m) => m[1]));

const names = fs
  .readdirSync(ACTIVE, { withFileTypes: true })
  .filter((d) => (d.isDirectory() || d.isSymbolicLink()) && fs.existsSync(path.join(ACTIVE, d.name, "SKILL.md")))
  .map((d) => d.name)
  .sort();

const byStem = new Map();
for (const n of names) {
  const stem = n.split("-")[0];
  if (!byStem.has(stem)) byStem.set(stem, []);
  byStem.get(stem).push(n);
}

const families = [...byStem]
  .filter(([, members]) => members.length >= min)
  .map(([stem, members]) => ({
    stem,
    members,
    heads: members.filter((m) => routed.has(m)).sort((a, b) => (a === stem ? -1 : b === stem ? 1 : a.localeCompare(b))),
  }))
  .sort((a, b) => b.members.length - a.members.length || a.stem.localeCompare(b.stem));

if (json) {
  console.log(JSON.stringify(families, null, 2));
} else {
  console.log(`${names.length} skills, ${families.length} families of ${min}+ sharing a stem, ${families.filter((f) => f.heads.length === 0).length} with NO-HEAD\n`);
  for (const f of families) {
    const head = f.heads.length ? `head: ${f.heads.join(", ")}` : "NO-HEAD";
    console.log(`${String(f.members.length).padStart(3)}  ${f.stem.padEnd(14)} ${head}`);
    console.log(`     ${f.members.filter((m) => !f.heads.includes(m)).join(", ")}`);
  }
}
