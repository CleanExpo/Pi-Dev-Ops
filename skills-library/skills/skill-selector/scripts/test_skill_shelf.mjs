// Tests for skill_shelf.mjs. Every test spawns the real CLI with HOME pointed at a
// throwaway fixture, so nothing here can touch the real ~/.claude.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLI = path.join(HERE, "skill_shelf.mjs");
const SHA = "a".repeat(40);

function skill(dir, name, description, extra = "") {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, "SKILL.md"),
    `---\nname: ${name}\ndescription: ${description}\n${extra}---\n\n# ${name}\n\nBody of ${name}.\n`,
  );
}

function fixture() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "shelf-"));
  const active = path.join(home, ".claude/skills");
  const vault = path.join(home, ".claude/skill-vault");
  skill(path.join(active, "real-skill"), "real-skill", "A hand-written local skill that must never be deleted.");
  fs.writeFileSync(path.join(active, "real-skill/notes.txt"), "irreplaceable");
  skill(path.join(active, "entry-point"), "entry-point", "Router entry point for shipping work.");
  skill(path.join(active, "longtail-a"), "longtail-a", "Rarely used helper for spreadsheets.");
  skill(path.join(active, "longtail-b"), "longtail-b", "Rarely used helper for slide decks.");
  skill(path.join(active, "typed-only"), "typed-only", "Only the user runs this.", "disable-model-invocation: true\n");
  skill(path.join(vault, "ext/tdd-vault"), "tdd-vault", "Reference for a disciplined coding loop.");
  skill(path.join(vault, "ext/real-skill"), "real-skill", "Upstream skill whose name collides with a local one.");
  skill(path.join(vault, "ext/other-vault"), "other-vault", "Kubernetes cluster upgrades.");
  fs.writeFileSync(
    path.join(active, "index.md"),
    [
      "| Intent / trigger phrase | Canonical skill |",
      "|---|---|",
      '| "ship it" / "release the backlog" | `entry-point` |',
      '| "red green refactor" / "write the failing test first" | `tdd-vault` |',
      "",
    ].join("\n"),
  );
  fs.mkdirSync(path.join(active, "skill-watch"), { recursive: true });
  fs.writeFileSync(
    path.join(active, "skill-watch/external-skills.json"),
    JSON.stringify({
      skills: [
        { name: "good", repo: "file:///nonexistent/repo.git", pinned_sha: SHA, review: "read 18/09/2026", vault: true },
        { name: "noreview", repo: "file:///nonexistent/repo.git", pinned_sha: SHA, review: "", vault: true },
        { name: "nopin", repo: "file:///nonexistent/repo.git", pinned_sha: "main", review: "read", vault: true },
      ],
    }),
  );
  fs.writeFileSync(
    path.join(home, ".claude/settings.json"),
    JSON.stringify({ hooks: { Stop: [{ command: "x" }] }, permissions: { deny: ["Read(.env)"] } }, null, 2),
  );
  return { home, active, vault, ledger: path.join(home, ".local/state/skill-shelf/checkouts.json") };
}

function run(home, ...args) {
  const r = spawnSync(process.execPath, [CLI, ...args], {
    env: { ...process.env, HOME: home },
    encoding: "utf8",
  });
  return { code: r.status, out: r.stdout, err: r.stderr };
}

test("C1 find: task-phrased query returns the vault skill, inside the limit, and no-match says so", () => {
  const f = fixture();
  // Positive control and sensitivity in one: the description never says "refactor" or
  // "failing test", so this hit can only come from the router trigger phrases.
  const hit = run(f.home, "find", "write the failing test first then refactor", "--limit", "2", "--json");
  assert.equal(hit.code, 0, hit.err);
  const rows = JSON.parse(hit.out);
  assert.ok(rows.length >= 1 && rows.length <= 2, `limit not respected: ${rows.length}`);
  assert.equal(rows[0].name, "tdd-vault");
  assert.equal(rows[0].source, "vault");
  assert.ok(rows.every((r) => r.description.length <= 200), "descriptions must be clipped");
  const miss = run(f.home, "find", "zzzqqq xylophone", "--json");
  assert.equal(miss.code, 1);
  assert.match(miss.err, /no match/i);
});

test("C2 round trip: checkout links into the vault, checkin removes the link and nothing else", () => {
  const f = fixture();
  const before = fs.readFileSync(path.join(f.vault, "ext/tdd-vault/SKILL.md"), "utf8");
  const link = path.join(f.active, "tdd-vault");
  const out = run(f.home, "checkout", "tdd-vault");
  assert.equal(out.code, 0, out.err);
  assert.ok(fs.lstatSync(link).isSymbolicLink(), "checkout must create a symlink");
  assert.equal(fs.realpathSync(link), fs.realpathSync(path.join(f.vault, "ext/tdd-vault")));
  const ledger = JSON.parse(fs.readFileSync(f.ledger, "utf8"));
  assert.equal(ledger.checkouts.length, 1);
  assert.equal(ledger.checkouts[0].name, "tdd-vault");
  const back = run(f.home, "checkin", "tdd-vault");
  assert.equal(back.code, 0, back.err);
  assert.equal(fs.existsSync(link), false, "link must be gone after checkin");
  assert.equal(fs.readFileSync(path.join(f.vault, "ext/tdd-vault/SKILL.md"), "utf8"), before);
  assert.equal(JSON.parse(fs.readFileSync(f.ledger, "utf8")).checkouts.length, 0);
  // A checkout whose vault dir vanished leaves a dangling link; checkin must still return it.
  assert.equal(run(f.home, "checkout", "other-vault").code, 0);
  fs.rmSync(path.join(f.vault, "ext/other-vault"), { recursive: true });
  const dangling = run(f.home, "checkin", "other-vault");
  assert.equal(dangling.code, 0, dangling.err);
  assert.equal(fs.lstatSync(path.join(f.active, "other-vault"), { throwIfNoEntry: false }), undefined);
});

test("C3 never deletes: a real skill dir survives a colliding checkout and a forged checkin", () => {
  const f = fixture();
  const real = path.join(f.active, "real-skill");
  const collide = run(f.home, "checkout", "real-skill");
  assert.equal(collide.code, 3, collide.err);
  assert.ok(fs.lstatSync(real).isDirectory() && !fs.lstatSync(real).isSymbolicLink());
  // Forge a ledger row that claims skill-shelf created the real directory.
  fs.mkdirSync(path.dirname(f.ledger), { recursive: true });
  fs.writeFileSync(
    f.ledger,
    JSON.stringify({ checkouts: [{ name: "real-skill", link: real, target: path.join(f.vault, "ext/real-skill"), at: new Date().toISOString() }] }),
  );
  const forged = run(f.home, "checkin", "real-skill");
  assert.equal(forged.code, 3, forged.err);
  assert.match(forged.err, /refus/i);
  assert.equal(fs.readFileSync(path.join(real, "notes.txt"), "utf8"), "irreplaceable");
  assert.ok(fs.existsSync(path.join(real, "SKILL.md")));
  const all = run(f.home, "checkin", "--all");
  assert.equal(all.code, 3);
  assert.equal(fs.readFileSync(path.join(real, "notes.txt"), "utf8"), "irreplaceable");
  // Round-2 reviewer finding: a dangling link whose target string merely starts with the vault
  // path ("<vault>/../../...") must be refused. Only a target that resolves into the vault is ours.
  const escape = path.join(f.active, "escape");
  const escapeTarget = `${f.vault}/../../.ssh/no-such`; // not path.join: it would normalise the .. away
  fs.symlinkSync(escapeTarget, escape);
  fs.writeFileSync(
    f.ledger,
    JSON.stringify({ checkouts: [{ name: "escape", link: escape, target: escapeTarget, at: new Date().toISOString() }] }),
  );
  const escaped = run(f.home, "checkin", "escape");
  assert.equal(escaped.code, 3, escaped.err);
  assert.ok(fs.lstatSync(escape).isSymbolicLink(), "the escaping link must be left alone");
});

// A real local git repo to pull from: one skill, plus a symlink that points outside the repo.
function upstreamRepo(home) {
  const repo = path.join(home, "upstream");
  skill(path.join(repo, "skills/eng/alpha"), "alpha", "Upstream skill alpha.");
  fs.writeFileSync(path.join(home, "outside-secret.txt"), "must never reach the vault");
  fs.symlinkSync(path.join(home, "outside-secret.txt"), path.join(repo, "skills/eng/alpha/leak.txt"));
  const git = (...a) => spawnSync("git", ["-C", repo, ...a], { encoding: "utf8" });
  git("init", "-q");
  git("-c", "user.email=t@t", "-c", "user.name=t", "add", "-A");
  git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init");
  return { url: `file://${repo}`, sha: git("rev-parse", "HEAD").stdout.trim() };
}

test("C4 pull gate: unreviewed, unpinned or traversing entries are refused before any network call", () => {
  const f = fixture();
  const up = upstreamRepo(f.home);
  const reg = path.join(f.active, "skill-watch/external-skills.json");
  const entries = JSON.parse(fs.readFileSync(reg, "utf8"));
  entries.skills.push(
    { name: "real", repo: up.url, path: "skills", pinned_sha: up.sha, review: "read", vault: true },
    { name: "traversal", repo: up.url, path: "../..", pinned_sha: up.sha, review: "read", vault: true },
    { name: "absolute", repo: up.url, path: f.home, pinned_sha: up.sha, review: "read", vault: true },
    { name: "wrongpin", repo: up.url, path: "skills", pinned_sha: "b".repeat(40), review: "read", vault: true },
  );
  fs.writeFileSync(reg, JSON.stringify(entries));

  const noreview = run(f.home, "pull", "noreview");
  assert.equal(noreview.code, 3);
  assert.match(noreview.err, /review/i);
  const nopin = run(f.home, "pull", "nopin");
  assert.equal(nopin.code, 3);
  assert.match(nopin.err, /pinned_sha/i);
  // The reviewer's finding (18/09/2026): a `path` of ../.. copied the system temp dir into the vault.
  for (const bad of ["traversal", "absolute"]) {
    const r = run(f.home, "pull", bad);
    assert.equal(r.code, 3, `${bad}: ${r.err}`);
    assert.match(r.err, /path/i);
    assert.equal(fs.existsSync(path.join(f.vault, bad)), false, `${bad} must leave no vault dir`);
  }
  // Control 1: a well-formed entry passes the gate and only then fails, on the fetch.
  const good = run(f.home, "pull", "good");
  assert.notEqual(good.code, 3, "a well-formed entry must get past the gate");
  assert.match(good.err, /fetch/i);
  assert.equal(fs.existsSync(path.join(f.vault, "good")), false, "a failed pull must leave no vault dir");
  // Control 2: a real pull lands, the pinned commit is enforced, and the outward symlink is dropped.
  const wrong = run(f.home, "pull", "wrongpin");
  assert.notEqual(wrong.code, 0);
  assert.equal(fs.existsSync(path.join(f.vault, "wrongpin")), false);
  const real = run(f.home, "pull", "real");
  assert.equal(real.code, 0, real.err);
  assert.ok(fs.existsSync(path.join(f.vault, "real/eng/alpha/SKILL.md")));
  assert.equal(fs.existsSync(path.join(f.vault, "real/eng/alpha/leak.txt")), false, "symlink out of the repo must not be copied");
  assert.equal(run(f.home, "find", "upstream skill alpha", "--json").code, 0, "pulled skill must be searchable");
});

test("C5 overrides: dry-run writes nothing; --write backs up and only adds name-only rows", () => {
  const f = fixture();
  const settings = path.join(f.home, ".claude/settings.json");
  const before = fs.readFileSync(settings, "utf8");
  const dry = run(f.home, "overrides", "--json");
  assert.equal(dry.code, 0, dry.err);
  assert.equal(fs.readFileSync(settings, "utf8"), before, "dry-run must not write");
  const plan = JSON.parse(dry.out);
  assert.deepEqual(plan.name_only.sort(), ["longtail-a", "longtail-b", "real-skill"]);
  const wrote = run(f.home, "overrides", "--write", "--json");
  assert.equal(wrote.code, 0, wrote.err);
  const after = JSON.parse(fs.readFileSync(settings, "utf8"));
  const orig = JSON.parse(before);
  assert.deepEqual(after.hooks, orig.hooks);
  assert.deepEqual(after.permissions, orig.permissions);
  assert.equal(after.skillOverrides["entry-point"], undefined, "router entry-points stay fully listed");
  assert.equal(after.skillOverrides["typed-only"], undefined, "already-hidden skills are left alone");
  assert.equal(after.skillOverrides["longtail-a"], "name-only");
  assert.ok(Object.values(after.skillOverrides).every((v) => v === "name-only"));
  const backups = fs.readdirSync(path.dirname(settings)).filter((n) => n.startsWith("settings.json.bak-skill-shelf-"));
  assert.equal(backups.length, 1);
  assert.equal(fs.readFileSync(path.join(path.dirname(settings), backups[0]), "utf8"), before);
});

test("C6 stale sweep: only checkouts older than the cutoff are returned", () => {
  const f = fixture();
  assert.equal(run(f.home, "checkout", "tdd-vault").code, 0);
  assert.equal(run(f.home, "checkout", "other-vault").code, 0);
  const ledger = JSON.parse(fs.readFileSync(f.ledger, "utf8"));
  ledger.checkouts.find((c) => c.name === "tdd-vault").at = new Date(Date.now() - 48 * 3600e3).toISOString();
  fs.writeFileSync(f.ledger, JSON.stringify(ledger));
  const sweep = run(f.home, "checkin", "--stale", "24");
  assert.equal(sweep.code, 0, sweep.err);
  assert.equal(fs.existsSync(path.join(f.active, "tdd-vault")), false, "old checkout must be returned");
  assert.ok(fs.lstatSync(path.join(f.active, "other-vault")).isSymbolicLink(), "fresh checkout must stay");
});

test("C7 skill doc: SKILL.md names every verb and stays under the soft cap", () => {
  const doc = fs.readFileSync(path.join(HERE, "../SKILL.md"), "utf8");
  for (const verb of ["find", "checkout", "checkin", "pull"]) {
    assert.match(doc, new RegExp(`skill_shelf\\.mjs[^\\n]*\\b${verb}\\b`), `SKILL.md must show the ${verb} command`);
  }
  assert.ok(doc.split("\n").length <= 200, "SKILL.md is over the 200-line soft cap");
});
