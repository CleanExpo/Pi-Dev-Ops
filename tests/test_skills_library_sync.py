"""The library's own skills reach Mission Control, one home per skill, without changing any skill
it loads today (scripts/sync_skills_library.py, src/tao/skills.py)."""
import json
import os
import shutil
import subprocess

import pytest

from scripts import sync_skills_library as sync
from src.tao import skills as tao_skills



def _commit(lib):
    """Commit the library checkout as it stands; return the commit."""
    def git(*args):
        return subprocess.run(["git", "-C", str(lib), *args], capture_output=True, text=True, check=True).stdout
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    return git("rev-parse", "HEAD").strip()


def _skill(root, name, body="Body.", description="Does a thing.", fm_name=None):
    (root / name).mkdir(parents=True)
    (root / name / "SKILL.md").write_text(f"---\nname: {fm_name or name}\ndescription: {description}\n---\n{body}\n")


@pytest.fixture()
def library(tmp_path):
    """A library checkout: two library skills, one vendored from PDO, one machine-local."""
    skills = tmp_path / "lib" / "skills"
    for name in ("alpha", "beta", "vendored", "local-only"):
        _skill(skills, name)
    (skills / "alpha" / "references").mkdir()
    (skills / "alpha" / "references" / "contract.md").write_text("Read me first.")
    (skills / "alpha" / "tests").mkdir()
    (skills / "alpha" / "tests" / "fixture.py").write_text("FAKE_KEY = 'sk-not-real'")
    (skills / "alpha" / "test_alpha.py").write_text("def test(): pass")
    (skills / "index.md").write_text("| \"say alpha\" | `alpha` |\n")
    for shared in ("README.md", "CLAUDE.md", "library/connections.md"):
        (skills / shared).parent.mkdir(exist_ok=True)
        (skills / shared).write_text("Shared.")
    homes = {"alpha": "library", "beta": "library", "vendored": "pi-dev-ops", "local-only": "machine-local"}
    (skills / "HOMES.json").write_text(json.dumps({"homes": homes, "aliases": {}}))
    subprocess.run(["git", "init", "-q", str(tmp_path / "lib")], check=True)
    return tmp_path / "lib"


@pytest.fixture()
def held_back(tmp_path, monkeypatch):
    """The test layout's own held-back list, empty unless a test writes one."""
    path = tmp_path / "held-back.txt"
    path.write_text("")
    monkeypatch.setattr(sync, "HELD_BACK", path)
    return path


@pytest.fixture()
def layout(tmp_path, library, held_back):
    dest, lock, pdo = tmp_path / "pdo" / "skills-library" / "skills", tmp_path / "pdo" / "lock", tmp_path / "pdo" / "skills"
    _skill(pdo, "vendored")
    sha = _commit(library)
    sync.sync(library, sha, dest=dest, lock=lock)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    return {"dest": dest, "lock": lock, "pdo": pdo, "baseline": baseline, "library": library, "sha": sha}


def _check(lay):
    return sync.check(dest=lay["dest"], pdo_skills=lay["pdo"], baseline=lay["baseline"], lock=lay["lock"])


def _resync(lay):
    sync.sync(lay["library"], _commit(lay["library"]), dest=lay["dest"], lock=lay["lock"])


def test_this_repos_copy_is_clean():
    """The committed skills-library/ matches its manifest, its lock, HOMES.json and the baseline."""
    assert sync.check() == []


def test_sync_copies_whole_library_skills_with_their_tests(layout):
    """Review round 1 P1-DEPENDENT-FILES-OMITTED: SKILL.md alone left out files the body requires.
    Round 2 P1-REQUIRED-SKILL-CONTROLS-OMITTED: so did leaving out the tests a body says to run."""
    dest = layout["dest"]
    assert sorted(p.name for p in dest.iterdir()) == ["CLAUDE.md", "HOMES.json", "README.md", "alpha", "beta",
                                                      "index.md", "library"]
    assert (dest / "library" / "connections.md").is_file()
    assert (dest / "alpha" / "references" / "contract.md").read_text() == "Read me first."
    assert (dest / "alpha" / "tests" / "fixture.py").is_file() and (dest / "alpha" / "test_alpha.py").is_file()
    manifest = json.loads((dest.parent / "MANIFEST.json").read_text())
    assert manifest["sha"] == layout["sha"] and "alpha/references/contract.md" in manifest["files"]
    assert layout["lock"].read_text() == layout["sha"] + "\n"
    assert _check(layout) == []


def test_a_held_back_skill_is_not_copied_and_must_be_a_library_skill(layout, held_back):
    """Review round 2 P1-REPO-SECRETS-GATE-FAILS: a skill whose files fail the repo's secrets gate
    stays out of the copy; the gate itself is not touched."""
    held_back.write_text("beta  # example values\n")
    _resync(layout)
    assert not (layout["dest"] / "beta").exists() and _check(layout) == []
    held_back.write_text("beta\nvendored  # not a library skill\n")
    assert "vendored: listed in held-back.txt but its home is not library; remove the line" in _check(layout)
    held_back.write_text("")
    assert "home=library but not copied: beta" in _check(layout)


def test_sync_replaces_what_was_there(layout):
    (layout["dest"] / "stale").mkdir()
    _resync(layout)
    assert not (layout["dest"] / "stale").exists()


def test_sync_copies_the_commit_not_the_working_tree(layout):
    """Review round 3 P1-SYNC-COPIES-IGNORED-UNCOMMITTED-FILES: a clean status still let an
    ignored file into the copy. Files now come from the pinned commit's objects."""
    lib, skills = layout["library"], layout["library"] / "skills"
    (lib / ".gitignore").write_text("*.secret\n")
    sha = _commit(lib)
    (skills / "alpha" / "private.secret").write_text("ignored")
    (skills / "alpha" / "untracked.md").write_text("untracked")
    (skills / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: x\n---\nEdited.\n")
    sync.sync(lib, sha, dest=layout["dest"], lock=layout["lock"])
    alpha = layout["dest"] / "alpha"
    assert not (alpha / "private.secret").exists() and not (alpha / "untracked.md").exists()
    assert "Body." in (alpha / "SKILL.md").read_text() and _check(layout) == []
    with pytest.raises(ValueError, match="cat-file"):
        sync.sync(lib, "f" * 40, dest=layout["dest"], lock=layout["lock"])
    assert layout["lock"].read_text() == sha + "\n"


def test_check_scans_copied_markdown_with_the_repo_scanners_rules(layout):
    """Review round 3 P1-MARKDOWN-SECRETS-BYPASS: the repo scanner skips .md, and skills are
    mostly Markdown. The key is built at run time so this file carries none."""
    notes = layout["dest"] / "alpha" / "references" / "contract.md"
    key = "AKIA" + "Q7XK2M9RT4WP8ZL3"
    notes.write_text("Example: AWS_KEY=" + key + "\n")
    assert any(p.startswith("secret-shaped value in the copy: alpha/references/contract.md:1")
               for p in _check(layout))
    # Review round 7 P1-MARKDOWN-PLACEHOLDER-LINE-BYPASS: a label on the line waives nothing.
    notes.write_text("Example (placeholder, not a real key): AWS_KEY=" + key + "\n")
    assert any(p.startswith("secret-shaped") for p in _check(layout)), "a label hid a real-shaped key"
    # Review round 8 P1-PLACEHOLDER-SUBSTRING-BYPASSES-COPIED-SECRET-GATE: a placeholder word
    # inside a key-shaped value waives nothing either.
    notes.write_text('API_KEY = "' + "k7Qx2Lm9Rt4Wp8Zn" + "placeholder" + "3Vb6Yc1Hd5Jf0Gs" + '"\n')
    assert any(p.startswith("secret-shaped") for p in _check(layout)), "a word inside the value hid it"
    notes.write_text('MYSQL_PWD="$' + 'MYSQLPASSWORD' + 'x7Qk2"\n')
    assert any(p.startswith("secret-shaped") for p in _check(layout)), "only a whole $NAME is a reference"
    notes.write_text('MYSQL_PWD="$' + 'MYSQLPASSWORD"\n')
    assert not any(p.startswith("secret-shaped") for p in _check(layout)), "a shell variable, not a value"
    notes.write_text("Example: AWS_KEY=" + "AKIA" + "IOSFODNN7EXAMPLE" + "\n")
    assert not any(p.startswith("secret-shaped") for p in _check(layout)), "the value itself is a placeholder"


def test_a_stale_staging_symlink_cannot_redirect_the_copy(layout, tmp_path):
    """Review round 4 P1-STAGED-SYMLINK-ESCAPES-COPY: a leftover skills.new symlink sent the sync's
    writes outside the repo and was installed as skills/, and check reported clean."""
    outside = tmp_path / "outside"
    outside.mkdir()
    dest = layout["dest"]
    (dest.parent / "skills.new").symlink_to(outside, target_is_directory=True)
    _resync(layout)
    assert list(outside.iterdir()) == [] and not dest.is_symlink()
    assert "not part of the copy (left by an interrupted sync?): skills.new" in _check(layout)
    (dest.parent / "skills.new").unlink()
    shutil.rmtree(dest)
    dest.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="through a symlink"):
        _resync(layout)
    assert list(outside.iterdir()) == []
    assert any(p.startswith("symlink where the copy should be") for p in _check(layout))


def test_sync_refuses_a_bad_sha_and_symlinks_at_any_level(layout, tmp_path):
    """Review round 1 P1-SYMLINKED-SKILL-DIRECTORY: a symlinked skill folder was followed."""
    with pytest.raises(ValueError):
        sync.sync(layout["library"], "main", dest=layout["dest"], lock=layout["lock"])
    outside = tmp_path / "outside"
    _skill(outside, "beta", body="from outside")
    src = layout["library"] / "skills"
    os.rename(src / "beta", tmp_path / "real-beta")
    os.symlink(outside / "beta", src / "beta")
    with pytest.raises(ValueError, match="symlink"):
        _resync(layout)
    os.remove(src / "beta")
    os.rename(tmp_path / "real-beta", src / "beta")
    os.symlink(tmp_path / "x.md", src / "beta" / "extra.md")
    with pytest.raises(ValueError, match="symlink"):
        _resync(layout)


def test_sync_refuses_an_empty_inventory_a_bad_name_or_a_renamed_skill(layout):
    """Review round 1 P1-VACUOUS-COPY-CHECK: an empty HOMES.json synced to an empty, clean copy."""
    homes_path = layout["library"] / "skills" / "HOMES.json"
    for homes, message in (({}, "no library skills"), ({"../x": "library"}, "plain folder name")):
        homes_path.write_text(json.dumps({"homes": homes}))
        with pytest.raises(ValueError, match=message):
            _resync(layout)
    homes_path.write_text(json.dumps({"homes": {"gamma": "library"}}))
    _skill(layout["library"] / "skills", "gamma", fm_name="gamma-renamed")
    with pytest.raises(ValueError, match="names a different skill"):
        _resync(layout)


def test_check_fails_on_a_changed_extra_or_missing_file(layout):
    (layout["dest"] / "alpha" / "references" / "contract.md").write_text("edited here")
    (layout["dest"] / "alpha" / "new.md").write_text("added here")
    (layout["dest"] / "index.md").unlink()
    problems = _check(layout)
    assert "changed since sync: alpha/references/contract.md" in problems
    assert "not in MANIFEST.json: alpha/new.md" in problems
    assert "missing from the copy: index.md" in problems
    assert "the copy has no index.md" in problems


def test_check_fails_when_the_manifest_and_lock_disagree(layout):
    layout["lock"].write_text("b" * 40 + "\n")
    assert any("MANIFEST.json was synced at" in p for p in _check(layout))
    layout["lock"].write_text("main\n")
    assert any("skills-library.lock is not a 40-char SHA" in p for p in _check(layout))


def test_check_fails_on_an_empty_copy_or_a_missing_baseline(layout):
    (layout["dest"] / "HOMES.json").write_text(json.dumps({"homes": {}}))
    assert "HOMES.json names no library skills" in _check(layout)
    layout["baseline"].unlink()
    assert "baseline.txt is missing" in _check(layout)


def test_check_fails_on_a_new_overlap_until_it_is_listed(layout):
    _skill(layout["pdo"], "alpha")
    assert any("alpha: its home is library" in p for p in _check(layout))
    _skill(layout["pdo"], "local-only")
    assert any("local-only: its home is machine-local" in p for p in _check(layout))
    layout["baseline"].write_text("alpha  # diverged\nlocal-only\n")
    assert _check(layout) == []


def test_check_fails_on_a_baseline_line_that_no_longer_overlaps(layout):
    layout["baseline"].write_text("beta  # merged long ago\n")
    assert any("beta: listed in" in p for p in _check(layout))


def test_check_fails_on_a_wrong_copy_or_a_symlink(layout, tmp_path):
    os.symlink(tmp_path / "x", layout["dest"] / "alpha" / "extra.md")
    _skill(layout["dest"], "vendored")
    problems = _check(layout)
    assert "copied but home is not library: vendored" in problems
    assert any(p.startswith("symlink in the copy") for p in problems)


def test_the_loader_reads_both_and_the_pdo_copy_wins(tmp_path, monkeypatch):
    _skill(tmp_path / "skills", "shared", body="PDO copy.")
    _skill(tmp_path / "skills", "pdo-only")
    _skill(tmp_path / "skills-library" / "skills", "shared", body="Library copy.")
    _skill(tmp_path / "skills-library" / "skills", "lib-only")
    monkeypatch.setattr(tao_skills, "_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(tao_skills, "_SKILLS_CACHE", None)
    loaded = tao_skills.load_all_skills()
    assert sorted(loaded) == ["lib-only", "pdo-only", "shared"]
    assert loaded["shared"]["body"] == "PDO copy."
    monkeypatch.setattr(tao_skills, "_SKILLS_CACHE", None)
    assert sorted(tao_skills.load_all_skills(str(tmp_path / "skills"))) == ["pdo-only", "shared"]


def test_mission_control_now_sees_the_library():
    """Real tree: library-only skills load; every PDO skill still loads from skills/."""
    tao_skills.invalidate_cache()
    try:
        loaded = tao_skills.load_all_skills()
        assert "nexus-recall" in loaded and "skills-library" in loaded["nexus-recall"]["path"]
        assert "/skills-library/" not in loaded["spm"]["path"]
    finally:
        tao_skills.invalidate_cache()


def test_a_routed_library_skill_can_reach_the_files_its_body_names(monkeypatch, tmp_path):
    """Review round 1 P1-DEPENDENT-FILES-OMITTED: "board review" pins ceo-board, whose body names
    references/board-members.md. The loaded context names the skill's folder, and the file is there.
    (It was shipyard until round 2 held that skill back; see .github/skills-library-held-back.txt.)"""
    import re
    from pathlib import Path

    from app.server import skill_routing

    monkeypatch.setenv("SKILL_ROUTER", "on")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(skill_routing, "LEDGER", tmp_path / "ledger.sqlite")
    monkeypatch.setattr(skill_routing, "_CATALOGUE", None)
    monkeypatch.setattr(skill_routing, "_PINS", None)
    tao_skills.invalidate_cache()
    context = skill_routing.skill_context("board review", "feature")
    assert "### Skill: ceo-board" in context
    folder = re.search(r"This skill's files are in (.+?); paths", context).group(1)
    assert "references/board-members.md" in context
    assert (Path(folder) / "references" / "board-members.md").is_file()
