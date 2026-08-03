"""
test_lessons_seed.py — the lesson store must survive a clean clone.

#607 untracked `.harness/` wholesale (609 files). `lessons.jsonl` went with it, so a fresh
checkout served an empty lesson list and the API smoke check
"Lessons list is non-empty (seed data present)" failed on every CI run.

These tests pin the repair. `test_seed_absent_yields_empty` is the positive control: without
it, a passing "non-empty" assertion could not distinguish a working seed from a test that
cannot fail.
"""
import json
import os

import pytest

from app.server import config, config_loader, lessons


@pytest.fixture
def runtime_store(tmp_path, monkeypatch):
    """Point the lesson store at a path that does not exist — CI's exact condition."""
    path = tmp_path / "harness" / "lessons.jsonl"
    monkeypatch.setattr(config, "LESSONS_FILE", str(path))
    assert not path.exists()
    return path


def test_seed_file_is_committed():
    """The seed must be in the repository, not merely on the author's machine."""
    assert config_loader.LESSONS_SEED_JSONL.is_file(), (
        f"lesson seed missing at {config_loader.LESSONS_SEED_JSONL} — a clean clone will "
        f"serve an empty lesson list, which is the #607 regression"
    )


def test_seed_is_valid_jsonl():
    lines = [
        ln for ln in
        config_loader.LESSONS_SEED_JSONL.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert lines, "seed file is empty"
    for i, line in enumerate(lines, 1):
        entry = json.loads(line)  # raises on malformed JSONL
        assert "lesson" in entry, f"seed line {i} has no 'lesson' field"


def test_clean_clone_yields_non_empty_lessons(runtime_store):
    """The assertion the CI smoke check makes: a fresh server has lessons."""
    assert len(lessons.load_lessons(limit=1000)) > 0


def test_seed_absent_yields_empty(tmp_path, monkeypatch):
    """POSITIVE CONTROL — with no seed reachable the store IS empty.

    If this ever passes while the seed is missing, the test above proves nothing.
    """
    monkeypatch.setattr(config, "LESSONS_FILE", str(tmp_path / "h" / "lessons.jsonl"))
    monkeypatch.setattr(
        config_loader, "LESSONS_SEED_JSONL", tmp_path / "no-such-seed.jsonl"
    )
    assert lessons.load_lessons(limit=1000) == []


def test_append_preserves_seeded_lessons(runtime_store):
    before = len(lessons.load_lessons(limit=1000))
    lessons.append_lesson("test", "unit-test", "appended after seeding", "info")
    assert len(lessons.load_lessons(limit=1000)) == before + 1


def test_seed_file_is_never_written(runtime_store):
    """The seed is committed config. Runtime writes go to the untracked store only."""
    before = config_loader.LESSONS_SEED_JSONL.read_bytes()
    lessons.append_lesson("test", "unit-test", "must not reach the seed", "info")
    assert config_loader.LESSONS_SEED_JSONL.read_bytes() == before


def test_existing_store_is_not_clobbered(tmp_path, monkeypatch):
    """Seeding must never overwrite a store that already has real history in it."""
    path = tmp_path / "harness" / "lessons.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({
            "ts": "2026-01-01T00:00:00Z", "source": "pre-existing",
            "category": "c", "lesson": "mine", "severity": "info",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "LESSONS_FILE", str(path))
    entries = lessons.load_lessons(limit=1000)
    assert len(entries) == 1
    assert entries[0]["source"] == "pre-existing"


def test_seed_survives_a_missing_parent_directory(runtime_store):
    """`.harness/` itself may not exist in a clean clone."""
    assert not os.path.isdir(os.path.dirname(str(runtime_store)))
    assert len(lessons.load_lessons(limit=1000)) > 0
    assert os.path.isfile(str(runtime_store))
