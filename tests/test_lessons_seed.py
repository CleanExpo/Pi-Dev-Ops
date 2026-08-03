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


# ── Review findings on f27f0c0e (codex, 2026-08-03) ──────────────────────────────────────

def test_reseeding_never_erases_an_append(runtime_store):
    """P1 data loss: a second seed must NOT clobber a store that already has appends.

    The reviewer demonstrated the original defect: `os.replace` is atomic but unconditional,
    so process A could seed and append while process B — which passed its existence check
    before A finished — replaced the whole store with a pristine seed copy, destroying A's
    append permanently. `os.link` refuses to overwrite, which is the property under test.
    """
    lessons.ensure_seeded()
    lessons.append_lesson("test", "unit-test", "must survive a reseed", "info")
    before = lessons.load_lessons(limit=1000)

    lessons.ensure_seeded()  # the racing process's second install attempt

    after = lessons.load_lessons(limit=1000)
    assert len(after) == len(before), "a reseed erased data — os.replace semantics are back"
    assert any(e.get("lesson") == "must survive a reseed" for e in after)


def test_seed_install_refuses_to_overwrite_a_populated_store(tmp_path, monkeypatch):
    """The no-clobber guarantee stated directly: an existing store is never replaced."""
    path = tmp_path / "harness" / "lessons.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00Z", "source": "live", "category": "c",
                    "lesson": "irreplaceable", "severity": "info"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "LESSONS_FILE", str(path))
    original = path.read_bytes()
    lessons.ensure_seeded()
    assert path.read_bytes() == original


def test_no_temp_files_are_left_behind(runtime_store):
    """The install writes a temp alongside the store; it must always be cleaned up."""
    lessons.ensure_seeded()
    leftovers = [p for p in os.listdir(os.path.dirname(str(runtime_store)))
                 if ".seed-" in p or p.endswith(".tmp")]
    assert leftovers == [], f"temp files left behind: {leftovers}"


def test_seed_failure_is_logged_not_silent(tmp_path, monkeypatch, caplog):
    """P2: a seeding fault must not be indistinguishable from an absent-by-design seed.

    The store is required by the smoke contract to be non-empty, so a permissions or disk
    fault here silently disables institutional memory on every read.
    """
    monkeypatch.setattr(config, "LESSONS_FILE", str(tmp_path / "h" / "lessons.jsonl"))

    def boom(*_a, **_k):
        raise PermissionError("denied")

    monkeypatch.setattr(lessons.shutil, "copyfile", boom)
    with caplog.at_level("ERROR"):
        lessons.ensure_seeded()
    assert any("seeding FAILED" in r.message or "seeding FAILED" in r.getMessage()
               for r in caplog.records), "seed failure produced no ERROR log"


def test_direct_writer_seeds_before_appending(tmp_path, monkeypatch):
    """P1: a direct writer that appends first would suppress the seed forever.

    `pipeline._append_ship_lesson` writes to the store without going through lessons.py.
    Once the file exists, seeding never runs again — so appending first permanently costs
    the 49 curated lessons.
    """
    from app.server import pipeline

    path = tmp_path / "harness" / "lessons.jsonl"
    monkeypatch.setattr(config, "LESSONS_FILE", str(path))
    # ONLY config.LESSONS_FILE is patched. Review of 7799bbfa found the earlier version of
    # this test also monkeypatched pipeline._HARNESS_ROOT into alignment, which masked the
    # writer appending to a different file from the one the seeder installs.

    pipeline._append_ship_lesson("pipeline-123", 9.0)

    entries = lessons.load_lessons(limit=1000)
    assert any(e.get("pipeline_id") == "pipeline-123" for e in entries), (
        "the writer appended somewhere other than the configured store — the paths split"
    )
    assert len(entries) > 1, (
        "direct writer suppressed the seed — the store holds only its own row"
    )


# ── Review findings on 7799bbfa (codex, 2026-08-03, review #3) ────────────────────────────

def test_losing_racer_reaches_the_publication_primitive_and_cannot_clobber(
    runtime_store, monkeypatch,
):
    """P0: the no-clobber property must be proven AT the publication primitive.

    test_reseeding_never_erases_an_append returns at the existence check on its second
    call, so it never reaches the install — reverting `os.link` to the clobbering
    `os.replace` would still pass it. This test simulates the actual race: a caller whose
    existence check went stale (said absent) while another caller installed and appended.
    It is forced all the way to the publication primitive, must lose gracefully, and must
    leave the store byte-identical.
    """
    lessons.ensure_seeded()
    lessons.append_lesson("test", "unit-test", "the losing racer must not destroy this", "info")
    before = runtime_store.read_bytes()

    real_exists = os.path.exists
    monkeypatch.setattr(
        lessons.os.path, "exists",
        lambda p: False if str(p) == str(config.LESSONS_FILE) else real_exists(p),
    )
    lessons._ensure_seeded()  # the stale check forces this call past line one to the install

    assert runtime_store.read_bytes() == before, (
        "the losing racer replaced the store — os.replace semantics are back"
    )


def test_feedback_writer_appends_to_the_configured_store(tmp_path, monkeypatch):
    """P1: feedback_loop's direct writer must seed AND write the same configured path.

    Like the pipeline writer, `_write_outcome_lesson` used a hardcoded `.harness/` path
    while the seeder honours config.LESSONS_FILE (the TAO_LESSONS override). Under an
    override deployment the first direct append created a second, unseeded store. Only
    config.LESSONS_FILE is patched here, so a re-split fails this test.
    """
    from app.server.agents import feedback_loop as fl

    path = tmp_path / "harness" / "lessons.jsonl"
    monkeypatch.setattr(config, "LESSONS_FILE", str(path))

    fl._write_outcome_lesson({"pipeline_id": "RA-999", "shipped_at": ""}, "positive")

    entries = lessons.load_lessons(limit=1000)
    assert any(e.get("pipeline_id") == "RA-999" for e in entries), (
        "the writer appended somewhere other than the configured store — the paths split"
    )
    assert len(entries) > 1, (
        "direct writer suppressed the seed — the store holds only its own row"
    )


# ── Review #5b finding on 4f2aee99 (codex, 2026-08-03) ───────────────────────────────────

def test_board_context_reader_follows_the_configured_store(tmp_path, monkeypatch):
    """P2: READERS must see the same store the seeder installs and the writers append to.

    board_meeting._read_lessons used a hardcoded .harness/ path while seeding and both
    writers honour config.LESSONS_FILE (the TAO_LESSONS override) — so under an override
    the board read a different, unseeded file. Only config.LESSONS_FILE is patched here.
    """
    from app.server.agents import board_meeting

    path = tmp_path / "override" / "lessons.jsonl"
    monkeypatch.setattr(config, "LESSONS_FILE", str(path))
    lessons.ensure_seeded()
    lessons.append_lesson("test", "unit-test", "visible to board context", "info")

    block = board_meeting._read_lessons(n=1000)
    assert "visible to board context" in block, (
        "board_meeting._read_lessons did not read the configured store"
    )


def test_prebrief_reader_follows_the_configured_store(tmp_path, monkeypatch):
    """P2: the board pre-brief must tail the configured store, not a hardcoded path."""
    import logging as _logging

    from app.server import cron_fire_agents as cfa
    from app.server import provider_router

    path = tmp_path / "override" / "lessons.jsonl"
    monkeypatch.setattr(config, "LESSONS_FILE", str(path))

    seen: list[str] = []

    def capture(p, since, max_lines=40):
        seen.append(str(p))
        return []

    monkeypatch.setattr(cfa, "_tail_jsonl_recent", capture)
    monkeypatch.setattr(cfa, "_fetch_urgent_high_tickets", lambda: [])
    monkeypatch.setattr(cfa, "_sprinkle_log", lambda *a, **k: None)

    def router_down(*_a, **_k):
        raise RuntimeError("stubbed — the reader path is what is under test")

    monkeypatch.setattr(provider_router, "run_via_provider_blocking", router_down)

    cfa._generate_board_prebrief(_logging.getLogger("test"))

    assert seen and seen[0] == str(path), (
        "the pre-brief tailed a path other than the configured store"
    )


def test_unreadable_seed_is_logged_not_silent(tmp_path, monkeypatch, caplog):
    """P2: an INACCESSIBLE seed must not be mistaken for a deliberately absent one.

    Path.is_file() swallows OSError into False, so an unreadable seed took the silent
    absent-by-design branch and the ERROR handler never ran. The lookup now uses stat(),
    which keeps the two cases apart.
    """
    monkeypatch.setattr(config, "LESSONS_FILE", str(tmp_path / "h" / "lessons.jsonl"))
    seed = str(config_loader.LESSONS_SEED_JSONL)
    real_stat = os.stat

    def stat_denied(p, *a, **k):
        if str(p) == seed:
            raise PermissionError(13, "Permission denied", str(p))
        return real_stat(p, *a, **k)

    monkeypatch.setattr(lessons.os, "stat", stat_denied)
    with caplog.at_level("ERROR"):
        lessons.ensure_seeded()
    assert any("UNREADABLE" in r.getMessage() for r in caplog.records), (
        "an unreadable seed produced no ERROR log — it read as absent-by-design"
    )
