#!/usr/bin/env python3
"""Tests for review_supersede: older review rounds of one rv-<stream> close, everything else stays.
Run: python3 test_review_supersede.py"""
import json, os, shutil, subprocess, sys, tempfile, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "scripts", "review_supersede.py")


def card(i, status, claimed, created, updated="2026-11-01T00:00:00+00:00"):
    # `created` ranks a round; `updated` is a later edit time and must never decide it.
    return {"id": i, "status": status, "claimed_by": claimed, "created": created,
            "updated": updated, "title": i}


BOARD = {"jobs": [
    card("A1", "review", "Codex rv-ccw-golive-2154617", "2026-10-27T01:02:45+00:00"),
    card("A2", "review", "Codex rv-ccw-golive-28d8b99", "2026-10-27T11:13:19+10:00"),  # == 01:13Z
    card("A3", "doing", "Codex rv-ccw-golive-7af8e6e9", "2026-10-27T19:08:47+00:00"),
    card("B1", "review", "Codex rv-ug-cron-49a214d", "2026-10-27T23:10:33+00:00"),
    card("B2", "review", "Codex rv-ug-cron-77ce905", "2026-10-28T09:32+1000"),
    card("C1", "review", "Codex rv-optix-532faac", "2026-10-27T12:00:13+00:00"),
    card("C2", "review", "Codex rv-optix-8e60f7d", "not a time"),
    card("D1", "review", "Codex rv-solo-abc1234", "2026-10-27T12:00:13+00:00"),
    card("E1", "review", "Phill", "2026-10-20T00:00:00+00:00"),
    card("E2", "review", "Phill", "2026-10-21T00:00:00+00:00"),
]}


def run(path, *args):
    return subprocess.run([sys.executable, "-B", SCRIPT, "--jobs", path, *args],
                          capture_output=True, text=True, check=True).stdout


def status(path):
    return {j["id"]: (j["status"], j.get("superseded_by")) for j in json.load(open(path))["jobs"]}


def test_dry_run_changes_nothing(tmp):
    p = os.path.join(tmp, "jobs.json"); json.dump(BOARD, open(p, "w"))
    before = open(p).read()
    out = run(p)
    assert "would close A1" in out and "3 superseded" in out, out
    assert open(p).read() == before


def test_apply_closes_only_older_rounds_in_a_stream(tmp):
    p = os.path.join(tmp, "jobs.json"); json.dump(BOARD, open(p, "w"))
    run(p, "--apply")
    s = status(p)
    assert s["A1"] == ("done", "A3") and s["A2"] == ("done", "A3"), s
    assert s["A3"] == ("doing", None), s          # newest stands, whatever its status
    assert s["B1"] == ("done", "B2") and s["B2"] == ("review", None), s  # +1000 offset parsed
    assert s["C1"][0] == "review" and s["C2"][0] == "review", s  # unparseable stream untouched
    assert s["D1"] == ("review", None), s          # a single round is not superseded
    assert s["E1"] == ("review", None) and s["E2"] == ("review", None), s  # no rv- stream


def test_apply_is_idempotent(tmp):
    p = os.path.join(tmp, "jobs.json"); json.dump(BOARD, open(p, "w"))
    run(p, "--apply")
    assert "0 superseded" in run(p, "--apply")


def _apply_board(tmp, jobs):
    p = os.path.join(tmp, "jobs.json"); json.dump({"jobs": jobs}, open(p, "w"))
    run(p, "--apply")
    return status(p)


# Review of eeb5bcab: each of these closed the LIVE round.
def test_bad_created_leaves_the_stream_alone(tmp):
    s = _apply_board(tmp, [card("OLD", "review", "Codex rv-alpha-1111111", "2026-10-02T00:00:00+00:00"),
                           card("LIVE", "review", "Codex rv-alpha-2222222", "invalid"),
                           card("OLDB", "review", "Codex rv-beta-4444444", "2026-10-02T00:00:00+00:00"),
                           card("NAIVE", "review", "Codex rv-beta-3333333", "2026-10-03T00:00:00")])
    missing = card("NOCREATED", "review", "Codex rv-gamma-5555555", "x")
    del missing["created"]
    s.update(_apply_board(tmp, [missing, card("OLDG", "review", "Codex rv-gamma-6666666",
                                              "2026-10-02T00:00:00+00:00")]))
    assert all(v == ("review", None) for v in s.values()), s


# Review of 6e575cff: these closed the LIVE round.
def test_an_edited_older_card_never_outranks_the_live_round(tmp):
    s = _apply_board(tmp, [
        card("OLD", "review", "Codex rv-beta-1111111", "2026-10-01T00:00:00+00:00",
             updated="2026-10-03T00:00:00+00:00"),
        card("LIVE", "review", "Codex rv-beta-2222222", "2026-10-02T00:00:00+00:00",
             updated="2026-10-02T00:00:00+00:00")])
    assert s["LIVE"] == ("review", None) and s["OLD"] == ("done", "LIVE"), s


def test_a_duplicate_id_leaves_the_stream_alone(tmp):
    p = os.path.join(tmp, "jobs.json")
    json.dump({"jobs": [card("SAME", "review", "Codex rv-beta-1111111", "2026-10-01T00:00:00Z"),
                        card("SAME", "review", "Codex rv-beta-2222222", "2026-10-02T00:00:00Z"),
                        card("OK1", "review", "Codex rv-delta-1111111", "2026-10-01T00:00:00Z"),
                        card("OK2", "review", "Codex rv-delta-2222222", "2026-10-02T00:00:00Z")]},
              open(p, "w"))
    run(p, "--apply")
    jobs = json.load(open(p))["jobs"]
    assert [j["status"] for j in jobs[:2]] == ["review", "review"], jobs[:2]
    assert not any(j.get("superseded_by") for j in jobs[:2]), jobs[:2]
    assert jobs[2]["superseded_by"] == "OK2" and jobs[3]["status"] == "review", jobs[2:]  # others still sweep


# Review of 83b573c2.
def test_an_existing_closed_note_survives(tmp):
    old = card("OLD", "review", "Codex rv-beta-1111111", "2026-10-01T00:00:00Z")
    old["closed_note"] = "Retain founder note"
    p = os.path.join(tmp, "jobs.json")
    json.dump({"updated": "2026-10-01T00:00:00+00:00",
               "jobs": [old, card("NEW", "review", "Codex rv-beta-2222222", "2026-10-02T00:00:00Z")]},
              open(p, "w"))
    run(p, "--apply")
    d = json.load(open(p))
    j = next(x for x in d["jobs"] if x["id"] == "OLD")
    assert j["closed_note"] == "Retain founder note" and j["superseded_by"] == "NEW", j
    assert "NEW" in j["supersede_note"], j
    assert d["updated"] != "2026-10-01T00:00:00+00:00", d["updated"]  # board stamp refreshed


def test_a_marked_but_open_card_still_closes(tmp):
    s = _apply_board(tmp, [
        dict(card("OLDEST", "review", "Codex rv-beta-0000000", "2026-10-01T00:00:00Z"), superseded_by="MIDDLE"),
        card("MIDDLE", "review", "Codex rv-beta-1111111", "2026-10-02T00:00:00Z"),
        card("LIVE", "review", "Codex rv-beta-2222222", "2026-10-03T00:00:00Z")])
    assert s["OLDEST"] == ("done", "LIVE") and s["MIDDLE"] == ("done", "LIVE"), s
    assert s["LIVE"] == ("review", None), s


def test_a_rerun_of_the_same_head_supersedes_nothing(tmp):
    s = _apply_board(tmp, [card("FIRST", "review", "Mac/codex rv-dr-4ca95f36", "2026-10-31T23:34:07Z"),
                           card("RERUN", "doing", "MacBook Codex rv-dr-4ca95f36", "2026-11-01T09:59:49+10:00"),
                           card("OLDHEAD", "review", "Codex rv-dr-1234567", "2026-10-30T00:00:00Z")])
    assert s["FIRST"] == ("review", None), s
    assert s["OLDHEAD"] == ("done", "RERUN"), s  # a different, older head still closes


def test_a_rerun_named_with_a_shorter_sha_is_the_same_head(tmp):
    full = "15d704f4c2f46a0224590da9d89aa15a11d4ff76"
    s = _apply_board(tmp, [card("FIRST", "review", f"Codex rv-x-{full}", "2026-10-01T00:00:00Z"),
                           card("RERUN", "doing", "Codex rv-x-15d704f", "2026-10-02T00:00:00Z"),
                           card("SHORTFIRST", "review", "Codex rv-y-15d704f", "2026-10-01T00:00:00Z"),
                           card("LONGRERUN", "doing", f"Codex rv-y-{full}", "2026-10-02T00:00:00Z")])
    assert s["FIRST"] == ("review", None) and s["SHORTFIRST"] == ("review", None), s


def test_a_note_never_assigns_a_stream(tmp):
    other = card("UNRELATED", "review", "Phill", "2026-10-01T00:00:00+00:00")
    other["note"] = "Discussed rv-alpha-1111111 elsewhere"
    s = _apply_board(tmp, [other, card("REAL", "review", "Codex rv-alpha-2222222",
                                       "2026-10-02T00:00:00+00:00")])
    assert s["UNRELATED"] == ("review", None), s


def test_a_tie_for_newest_leaves_the_stream_alone(tmp):
    s = _apply_board(tmp, [card("LIVE", "review", "Codex rv-alpha-2222222", "2026-10-02T00:00:00Z"),
                           card("OLD", "review", "Codex rv-alpha-1111111", "2026-10-02T00:00:00Z"),
                           card("OLDER", "review", "Codex rv-alpha-0000000", "2026-10-01T00:00:00Z")])
    assert all(v == ("review", None) for v in s.values()), s


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            tmp = tempfile.mkdtemp()
            try:
                fn(tmp); print("PASS", name)
            except Exception:
                failed += 1; print("FAIL", name); traceback.print_exc()
            finally:
                shutil.rmtree(tmp)
    sys.exit(1 if failed else 0)
