// Guards for the estate's enhanced `teach` skill and the /spm skill-loadout layer that routes
// to it. Reads THIS checkout, never the live ~/.claude.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const TEACH = path.resolve(HERE, "..");
const SKILLS = path.resolve(TEACH, "..");
const read = (p) => fs.readFileSync(p, "utf8");

function frontmatter(md) {
  const m = md.match(/^---\n([\s\S]*?)\n---\n/);
  assert.ok(m, "SKILL.md must open with frontmatter");
  return Object.fromEntries(m[1].split("\n").filter((l) => /^[a-z-]+:/.test(l)).map((l) => {
    const i = l.indexOf(":");
    return [l.slice(0, i), l.slice(i + 1).trim().replace(/^"|"$/g, "")];
  }));
}

// What a reader sees: no HTML comments and no fenced code (``` or ~~~). A row that exists only
// inside either is a decoy, not a lane (review rounds 2 and 3).
// What a reader sees, from a real CommonMark parser (markdown-it-py, installed by CI): only real
// anchors, list items, table cells and visible text count. Regex views kept accepting decoys a
// renderer never shows (core reviews r2 to r6: comments, fences, code spans, indented code, raw
// HTML, attributes, images). Fails closed when the parser is unavailable.
const MD_VIEW = path.join(TEACH, "scripts", "md_view.py");
function mdView(md) {
  const out = spawnSync("python3", [MD_VIEW], { input: md, encoding: "utf8" });
  assert.equal(out.status, 0, `md_view.py must parse the Markdown: ${out.stderr}`);
  return JSON.parse(out.stdout);
}

// Frontmatter parsed by a real YAML parser (PyYAML, installed by CI), so a quoted key, True,
// yes or on cannot slip past a regex (review round 3, P0-TEACH-YAML-QUOTED-DISABLE-ESCAPE).
// Fails closed when the parser is unavailable.
function yamlFrontmatter(md) {
  const m = md.match(/^---\n([\s\S]*?)\n---\n/);
  assert.ok(m, "SKILL.md must open with frontmatter");
  const out = spawnSync("python3", ["-c", "import sys, json, yaml; print(json.dumps(yaml.safe_load(sys.stdin.read())))"],
    { input: m[1], encoding: "utf8" });
  assert.equal(out.status, 0, `YAML frontmatter must parse with PyYAML: ${out.stderr}`);
  return JSON.parse(out.stdout);
}

// Rows of the first table in the section whose heading starts with `heading`; a table under
// another heading never counts (review round 5, P0-SPM-LANE-TABLE-CROSSES-HEADING).
function tableRows(view, heading) {
  const section = view.sections.find((x) => x.heading.startsWith(heading));
  assert.ok(section, `heading not found: ${heading}`);
  return (section.tables[0] ?? []).slice(1);
}

test("T1 teach SKILL.md: model-invocable so /spm can load it, high effort, within the size cap", () => {
  const md = read(path.join(TEACH, "SKILL.md"));
  const fm = frontmatter(md);
  assert.equal(fm.name, "teach");
  // /spm's Learn lane loads teach with the Skill tool; a user-only skill cannot be loaded that
  // way (review finding P1-LEARN-INVOCATION, 18/10/2026).
  // Absent from the PARSED frontmatter, however it is spelled or quoted (review rounds 2 and 3).
  const parsed = yamlFrontmatter(md);
  assert.ok(!("disable-model-invocation" in parsed), "teach must be loadable by /spm's Learn lane: no disable-model-invocation key");
  assert.equal(parsed.name, "teach");
  assert.match(fm.description, /Use when /, "a model-invoked description says when to use it");
  assert.match(fm.description, /Not for a single explanation/, "it must carry the negative trigger");
  assert.ok(fm.description.length <= 500, `router entry-point description must be <=500 chars, got ${fm.description.length}`);
  assert.ok(["high", "xhigh", "max"].includes(parsed.effort), `effort must be high or above (as YAML reads it), got ${parsed.effort}`);
  assert.equal(parsed.description, fm.description, "the description the tests read must be the one YAML reads");
  assert.ok(md.split("\n").length <= 200, "SKILL.md must stay within the 200-line library cap");
});

test("T2 every reference teach links exists; glossary linked; lessons link assets one folder up", () => {
  const view = mdView(read(path.join(TEACH, "SKILL.md")));
  const links = view.links.filter((h) => !/^https?:/.test(h)).map((h) => h.replace(/#.*$/, ""));
  assert.ok(links.length >= 5, `expected links to the format references and assets, got ${links.length}`);
  const missing = links.filter((l) => !fs.existsSync(path.join(TEACH, l)));
  assert.deepEqual(missing, [], `links to files that do not exist: ${missing.join(", ")}`);
  assert.ok(links.some((l) => /glossary-format\.md$/.test(l)), "GLOSSARY format must be linked from SKILL.md");
  // The link must be the Format cell of the GLOSSARY.md workspace row, not anywhere in the file
  // (core review r7, P0-TEACH-GLOSSARY-TABLE-LINK-FALSE-GREEN).
  // Only the first table of the Teaching workspace section counts (core review r8: an unrelated
  // earlier table with a linked GLOSSARY.md row satisfied the old check).
  const glossaryRows = tableRows(view, "Teaching workspace").filter((r) => r[0] === "`GLOSSARY.md`");
  // Exactly one row: a second, conflicting row must never hide behind the first (core review r9).
  assert.equal(glossaryRows.length, 1, `the workspace table needs exactly one \`GLOSSARY.md\` row, found ${glossaryRows.length}`);
  const glossaryRow = glossaryRows[0];
  assert.equal(glossaryRow[2], "[glossary-format.md](references/glossary-format.md)", "GLOSSARY.md's Format cell must link its format reference");
  // Lessons live in lessons/, assets in the workspace root (review finding P1-TEACH-ASSET-PATH).
  assert.match(view.text, /`\.\.\/assets\/lesson\.css`/);
  assert.match(view.text, /`\.\.\/assets\/quiz\.js`/);
  assert.doesNotMatch(view.text, /linking `assets\//, "a lesson linking assets/ resolves to lessons/assets/");
});

test("T3 provenance pins the exact upstream commit and keeps the upstream licence", () => {
  const prov = read(path.join(TEACH, "PROVENANCE.md"));
  assert.match(prov, /mattpocock\/skills/);
  const provView = mdView(prov);
  const sections = provView.sections;
  // Every rendered "Pinned commit" label counts, in a list item, paragraph or table (core review r9).
  const labels = provView.text.match(/Pinned commit/g) ?? [];
  assert.equal(labels.length, 1, `PROVENANCE.md must show exactly one 'Pinned commit' label, found ${labels.length}`);
  // The opening section must be Provenance: nothing may be prepended above it (core review r9).
  assert.equal(sections.find((x) => x.heading)?.heading, "Provenance", "the first rendered heading must be Provenance");
  const pins = sections.flatMap((x) => x.items.filter((i) => /^Pinned commit:/.test(i)).map((i) => [x.heading, i]));
  // Exactly one pin, in the document's opening Provenance section: a second (superseded or decoy)
  // pin must never decide what the test reads (core review r8).
  assert.equal(pins.length, 1, `PROVENANCE.md must carry exactly one 'Pinned commit' item, found ${pins.length}`);
  assert.equal(pins[0][0], "Provenance", "the pin belongs to the opening Provenance section");
  const pinned = pins[0][1].match(/^Pinned commit: `([0-9a-f]{40})`/);
  assert.ok(pinned, "PROVENANCE.md needs a rendered '- Pinned commit: `<40-char sha>`' list item");
  assert.equal(pinned[1], "ad5400b930b297b0c0cb231ff1ffe42a7da666aa", "the Pinned commit field must be the reviewed upstream SHA");
  assert.match(read(path.join(TEACH, "LICENSE")), /MIT License/);
});

// mulberry32: a well-mixed seeded PRNG, so the test measures the shuffle, not a weak generator.
function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function loadQuiz(seed, document) {
  const ctx = { window: { document }, Math: Object.assign(Object.create(Math), { random: seeded(seed) }) };
  vm.createContext(ctx);
  vm.runInContext(read(path.join(TEACH, "assets", "quiz.js")), ctx);
  assert.equal(typeof ctx.window.TeachQuiz?.shuffleOptions, "function", "assets/quiz.js must expose window.TeachQuiz.shuffleOptions");
  return ctx.window.TeachQuiz;
}

test("T4 the shuffle is complete and uniform for 2 to 5 options, and tracks the correct answer", () => {
  // Review finding P1-QUIZ-GUARD-FALSE-PASS: a 3-option bypass and a biased shuffle
  // ([2,11,43,144] over 200 seeds) both passed the first version of this test.
  const RUNS = 600;
  for (const n of [2, 3, 4, 5]) {
    const options = Array.from({ length: n }, (_, i) => (i === 0 ? "right" : `wrong ${i}`));
    const counts = new Array(n).fill(0);
    for (let seed = 1; seed <= RUNS; seed++) {
      const out = loadQuiz(seed).shuffleOptions(options, 0);
      assert.deepEqual([...out.options].sort(), [...options].sort(), "shuffle must not drop or invent options");
      assert.equal(out.options[out.correctIndex], "right", "correctIndex must follow the correct answer");
      counts[out.correctIndex]++;
    }
    const expected = RUNS / n;
    for (const c of counts) {
      assert.ok(c > expected * 0.7 && c < expected * 1.3, `n=${n}: correct-answer slots must be near-uniform, got [${counts}] (expected ~${expected.toFixed(0)} each)`);
    }
  }
});

// A DOM just big enough for quiz.js: buttons, a feedback line, a .quiz container.
function fakeQuizDom(labels) {
  const mk = (html) => {
    const handlers = [];
    const classes = new Set();
    return { innerHTML: html, hidden: true, textContent: "", classList: { add: (c) => classes.add(c), has: (c) => classes.has(c) },
      addEventListener: (ev, fn) => ev === "click" && handlers.push(fn), click: () => handlers.forEach((fn) => fn()) };
  };
  const buttons = labels.map(mk);
  const feedback = mk("");
  const quiz = { dataset: { correct: "0" }, querySelectorAll: (s) => (s === "button" ? buttons : []), querySelector: (s) => (s === ".feedback" ? feedback : null) };
  let ready = null;
  const document = {
    addEventListener: (ev, fn) => { if (ev === "DOMContentLoaded") ready = fn; },
    querySelectorAll: (s) => (s === ".quiz" ? [quiz] : []),
  };
  return { document, buttons, feedback, fire: () => ready && ready() };
}

test("T4c every ordering of the options is reachable and near-uniform, not just the answer's slot", () => {
  // Review round 7 (P0-TEACH-FULL-SHUFFLE-GUARD-FALSE-GREEN): inserting the correct answer at a
  // random slot while keeping the wrong answers in their original order passed T4. A true
  // shuffle reaches every one of the n! orderings about equally often.
  for (const [n, runs] of [[3, 1200], [4, 4800]]) {
    const options = Array.from({ length: n }, (_, i) => `o${i}`);
    const counts = new Map();
    for (let seed = 1; seed <= runs; seed++) {
      const key = loadQuiz(seed).shuffleOptions(options, 0).options.join(",");
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    const perms = [...Array(n).keys()].reduce((a, i) => a * (i + 1), 1);
    assert.equal(counts.size, perms, `n=${n}: expected all ${perms} orderings, saw ${counts.size}`);
    const expected = runs / perms;
    for (const [k, c] of counts) assert.ok(c > expected * 0.6 && c < expected * 1.4, `n=${n}: ordering ${k} seen ${c} times, expected ~${expected}`);
  }
});

test("T4d every option reaches every slot near-uniformly for 2 to 6 options", () => {
  // Core review r1: a 5-option quiz that kept the wrong answers in order passed T4/T4c, which
  // only covered n=3 and n=4 orderings. Per-option, per-slot frequencies catch any n.
  const RUNS = 1500;
  for (const n of [2, 3, 4, 5, 6]) {
    const options = Array.from({ length: n }, (_, i) => `o${i}`);
    const grid = options.map(() => new Array(n).fill(0));
    for (let seed = 1; seed <= RUNS; seed++) {
      const out = loadQuiz(seed + 7919 * n).shuffleOptions(options, 0).options;
      out.forEach((o, slot) => grid[Number(o.slice(1))][slot]++);
    }
    const expected = RUNS / n;
    grid.forEach((row, o) => row.forEach((c, slot) =>
      assert.ok(c > expected * 0.65 && c < expected * 1.35, `n=${n}: option ${o} in slot ${slot} ${c} times, expected ~${expected.toFixed(0)}`)));
  }
});

test("T4e for 5 and 6 options, pair order is a coin flip and nearly every ordering is reached", () => {
  // Core review r2: a random cyclic rotation fills every slot evenly (T4d passes) but reaches only
  // n of n! orderings. In a true shuffle each pair of options appears in either order half the
  // time, and 1500 shuffles reach nearly all 120 orderings of 5 and most of the 720 of 6.
  const RUNS = 1500;
  for (const n of [5, 6]) {
    const options = Array.from({ length: n }, (_, i) => `o${i}`);
    const before = options.map(() => new Array(n).fill(0));
    const seen = new Set();
    for (let seed = 1; seed <= RUNS; seed++) {
      const out = loadQuiz(seed + 104729 * n).shuffleOptions(options, 0).options;
      seen.add(out.join(","));
      const pos = Object.fromEntries(out.map((o, i) => [o, i]));
      for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) if (a !== b && pos[`o${a}`] < pos[`o${b}`]) before[a][b]++;
    }
    for (let a = 0; a < n; a++) for (let b = a + 1; b < n; b++) {
      const share = before[a][b] / RUNS;
      assert.ok(share > 0.42 && share < 0.58, `n=${n}: o${a} before o${b} in ${(share * 100).toFixed(0)}% of runs, expected ~50%`);
    }
    // 1500 uniform draws from n! orderings reach n!(1 - e^(-1500/n!)) on average: ~119 of 120 and
    // ~630 of 720. The floors sit far below that and far above any rotation/reversal family
    // (core review r3, P0-TEACH-SIX-OPTION-SHUFFLE-FALSE-GREEN).
    const floor = { 5: 110, 6: 560 }[n];
    assert.ok(seen.size >= floor, `n=${n}: only ${seen.size} orderings reached in ${RUNS} shuffles (floor ${floor})`);
  }
});

test("T4b quiz.js mounts itself on page load, shuffles the buttons, and marks answers", () => {
  const labels = ["Correct answer", "Wrong one", "Wrong two"];
  let moved = 0;
  for (let seed = 1; seed <= 60; seed++) {
    const dom = fakeQuizDom(labels);
    loadQuiz(seed, dom.document);
    dom.fire();
    const shown = dom.buttons.map((b) => b.innerHTML);
    assert.deepEqual([...shown].sort(), [...labels].sort(), "mounting must keep every option");
    const right = shown.indexOf("Correct answer");
    if (right !== 0) moved++;
    dom.buttons[(right + 1) % 3].click();
    assert.ok(dom.buttons[(right + 1) % 3].classList.has("wrong"), "a wrong answer is marked wrong");
    dom.buttons[right].click();
    assert.ok(dom.buttons[right].classList.has("right"), "the correct answer is marked right after shuffling");
    assert.equal(dom.feedback.textContent, "Correct.");
  }
  assert.ok(moved > 20, `mounting must actually move the authored-first answer, moved ${moved}/60`);
});

test("T5 /spm sizes a Learn lane row to teach and runs the skill loadout (find, checkout, check in)", () => {
  const view = mdView(read(path.join(SKILLS, "spm", "SKILL.md")));
  const spm = view.text;
  const rows = tableRows(view, "0. Size it first");
  const learn = rows.find((r) => r[1] === "Learn");
  assert.ok(learn, `the sizing table needs a **Learn** row, rows: ${rows.map((r) => r[1]).join(", ")}`);
  assert.match(learn[2], /`teach`/, "the Learn row must route to teach");
  // Search first, read-only before the Done contract is locked (core review r1), the shelf after.
  assert.match(spm, /grep -n -i '<verb>' ~\/\.claude\/skills\/index\.md/, "the loadout must search, not guess skills");
  assert.match(spm, /skill_shelf\.mjs find/);
  assert.match(spm, /checkout <name>/);
  assert.match(spm, /checkin <name>/, "the loadout must check its own skills back in when the task ends");
  // Review round 4: --all also unlinks other sessions' checkouts.
  assert.doesNotMatch(spm.replace(/Never `--all`[^.]*\./g, ""), /checkin --all/, "never instruct checkin --all");
  assert.match(spm, /`unslop`/, "every reader-facing output gets the canonical writing gate");
  assert.match(spm, /`effort`/, "the loadout records the mode (effort) each skill runs at");
});
