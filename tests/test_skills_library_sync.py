"""The library's own skills reach Mission Control, one home per skill, without changing any skill
it loads today (scripts/sync_skills_library.py, src/tao/skills.py)."""
import json
import os

import pytest

from scripts import sync_skills_library as sync
from src.tao import skills as tao_skills

SHA = "a" * 40


def _skill(root, name, body="Body.", description="Does a thing."):
    (root / name).mkdir(parents=True)
    (root / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}\n")


@pytest.fixture()
def library(tmp_path):
    """A library checkout: two library skills, one vendored from PDO, one machine-local."""
    skills = tmp_path / "lib" / "skills"
    for name in ("alpha", "beta", "vendored", "local-only"):
        _skill(skills, name)
    (skills / "alpha" / "references").mkdir()
    (skills / "alpha" / "references" / "big.md").write_text("not copied")
    (skills / "index.md").write_text("| \"say alpha\" | `alpha` |\n")
    homes = {"alpha": "library", "beta": "library", "vendored": "pi-dev-ops", "local-only": "machine-local"}
    (skills / "HOMES.json").write_text(json.dumps({"homes": homes, "aliases": {}}))
    return tmp_path / "lib"


@pytest.fixture()
def layout(tmp_path, library):
    dest, lock, pdo = tmp_path / "pdo" / "skills-library" / "skills", tmp_path / "pdo" / "lock", tmp_path / "pdo" / "skills"
    _skill(pdo, "vendored")
    sync.sync(library, SHA, dest=dest, lock=lock)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    return {"dest": dest, "lock": lock, "pdo": pdo, "baseline": baseline, "library": library}


def _check(lay):
    return sync.check(dest=lay["dest"], pdo_skills=lay["pdo"], baseline=lay["baseline"], lock=lay["lock"])


def test_this_repos_copy_is_clean():
    """The committed skills-library/ matches its own HOMES.json and the overlap baseline."""
    assert sync.check() == []


def test_sync_copies_only_library_skill_files_and_pins_the_sha(layout):
    dest = layout["dest"]
    assert sorted(p.name for p in dest.iterdir()) == ["HOMES.json", "alpha", "beta", "index.md"]
    assert [p.name for p in (dest / "alpha").iterdir()] == ["SKILL.md"]
    assert layout["lock"].read_text() == SHA + "\n"
    assert _check(layout) == []


def test_sync_replaces_what_was_there(layout):
    (layout["dest"] / "stale").mkdir()
    sync.sync(layout["library"], SHA, dest=layout["dest"], lock=layout["lock"])
    assert not (layout["dest"] / "stale").exists()


def test_sync_refuses_a_symlink_and_a_bad_sha(layout, tmp_path):
    with pytest.raises(ValueError):
        sync.sync(layout["library"], "main", dest=layout["dest"], lock=layout["lock"])
    beta = layout["library"] / "skills" / "beta" / "SKILL.md"
    beta.unlink()
    os.symlink(tmp_path / "elsewhere.md", beta)
    with pytest.raises(ValueError, match="symlink"):
        sync.sync(layout["library"], SHA, dest=layout["dest"], lock=layout["lock"])


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


def test_check_fails_on_a_wrong_copy(layout):
    (layout["dest"] / "beta" / "SKILL.md").unlink()
    (layout["dest"] / "beta").rmdir()
    _skill(layout["dest"], "vendored")
    problems = _check(layout)
    assert "home=library but not copied: beta" in problems
    assert "copied but home is not library: vendored" in problems


def test_check_fails_on_a_symlink_or_a_bad_lock(layout, tmp_path):
    os.symlink(tmp_path / "x", layout["dest"] / "alpha" / "extra.md")
    layout["lock"].write_text("main\n")
    problems = _check(layout)
    assert any(p.startswith("symlink in the copy") for p in problems)
    assert any("skills-library.lock" in p for p in problems)


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
