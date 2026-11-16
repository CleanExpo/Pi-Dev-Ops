"""RA-8100 D59: an answer must name EVERY part of what was asked, compared exactly.

Round 8 and the lead's probe showed five answers about something else that the reader accepted: each
identity row compared one part of the request (a number, a commit SHA, the tail of a URL) and nothing
required the repository to be compared too. The design rule tested here:

* every row of ``IDENTITY`` lists every part asked; each part is compared exactly with a field of the
  answer, or is listed in ``unchecked`` with the written reason the answer cannot name it; never both,
  never neither;
* every comparison kind is exact (no ends-with, starts-with or contains), ASCII only when case is folded;
* a caller cannot apply a row without passing every part asked.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from _delivery_reconcile_support import ALLOWED, ATO, SHA_A, good_pr_paths, install_fakes, run, setup_tick
from test_delivery_field_ticks import ENTRIES, FAKE_REVIEWER, REVIEW, _plant_state, _world

from app.server import delivery_collect as dc
from app.server import delivery_collect_fields as df
from app.server import delivery_collect_github as dg

BASE = f"/repos/{ATO}"
REVIEWS = f"{BASE}/pulls/5/reviews?per_page=100&page=1"
GOOD_URL = f"https://api.github.com{BASE}/pulls/5"
KELVIN = "K"  # lower-cases to "k": a non-ASCII letter must never equal an ASCII one


def _read(monkeypatch: pytest.MonkeyPatch, edit: object) -> str | None:
    st = install_fakes(monkeypatch)
    st.gh.update(good_pr_paths(ATO, 5))
    st.gh[REVIEWS] = [{"id": 1, "user": {"login": "someone", "type": "User"}, "state": "APPROVED",
                       "commit_id": SHA_A, "submitted_at": "2026-11-14T03:00:00Z", "pull_request_url": GOOD_URL}]
    edit(st.gh)  # type: ignore[operator]
    try:
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    except dc.Unknown as exc:
        return exc.reason
    return None


def _url(url: object):  # noqa: ANN202
    return lambda gh: gh[REVIEWS][0].__setitem__("pull_request_url", url)


def _pull(**fields: object):  # noqa: ANN202
    return lambda gh: gh[f"{BASE}/pulls/5"].update(fields)


def _status(**fields: object):  # noqa: ANN202
    return lambda gh: gh[f"{BASE}/commits/{SHA_A}/status"].update(fields)


OTHER = {"repo": {"full_name": "Other/repo"}}
ABOUT_SOMETHING_ELSE = [
    # the five answers the probe at 6bac6c64 showed were accepted
    ("review-query-tail", _url(f"https://api.github.com/repos/Other/repo/pulls/8?redirect={BASE}/pulls/5"), "review_mismatch"),
    ("review-other-host", _url(f"https://example.invalid{BASE}/pulls/5"), "review_mismatch"),
    ("review-nested-path", _url(f"https://api.github.com/repos/Other{BASE}/pulls/5"), "review_mismatch"),
    ("pull-other-repo", _pull(base=OTHER), "pull_mismatch"),
    ("status-other-repo", _status(repository={"full_name": "Other/repo"}), "status_mismatch"),
    # the same kind, every near miss of an exact comparison
    ("review-query", _url(GOOD_URL + "?x=1"), "review_mismatch"),
    ("review-bare-query", _url(GOOD_URL + "?"), "review_mismatch"),
    ("review-fragment", _url(GOOD_URL + "#x"), "review_mismatch"),
    ("review-trailing-slash", _url(GOOD_URL + "/"), "review_mismatch"),
    ("review-longer-number", _url(GOOD_URL + "0"), "review_mismatch"),
    ("review-leading-space", _url(" " + GOOD_URL), "review_mismatch"),
    ("review-newline", _url(GOOD_URL + "\n"), "review_mismatch"),
    ("review-http", _url(GOOD_URL.replace("https://", "http://")), "review_mismatch"),
    ("review-port", _url(GOOD_URL.replace("github.com", "github.com:443")), "review_mismatch"),
    ("review-user-part", _url(GOOD_URL.replace("https://", "https://api.github.com@")), "review_mismatch"),
    ("review-html-url", _url(f"https://github.com/{ATO}/pull/5"), "review_mismatch"),
    ("pull-repo-prefix", _pull(base={"repo": {"full_name": "X" + ATO}}), "pull_mismatch"),
    ("pull-repo-suffix", _pull(base={"repo": {"full_name": ATO + "-fork"}}), "pull_mismatch"),
    ("pull-repo-absent", _pull(base={"repo": {}}), "pull_mismatch"),
    ("pull-base-null", _pull(base=None), "pull_mismatch"),
    ("pull-repo-list", _pull(base={"repo": {"full_name": [ATO]}}), "pull_mismatch"),
    ("status-repo-absent", _status(repository={}), "status_mismatch"),
    ("status-repo-null", _status(repository=None), "status_mismatch"),
    ("status-repo-prefix", _status(repository={"full_name": "X" + ATO}), "status_mismatch"),
]


@pytest.mark.parametrize("edit,reason", [pytest.param(e, r, id=i) for i, e, r in ABOUT_SOMETHING_ELSE])
def test_an_answer_about_something_else_is_refused(monkeypatch: pytest.MonkeyPatch, edit: object, reason: str) -> None:
    assert _read(monkeypatch, edit) == reason


@pytest.mark.parametrize("edit", [
    pytest.param(lambda gh: None, id="as-built"),
    pytest.param(_url(GOOD_URL.upper().replace("HTTPS://API.GITHUB.COM", "https://api.github.com")), id="repo-case-differs"),
    pytest.param(_pull(base={"repo": {"full_name": ATO.upper()}}), id="pull-repo-case-differs"),
    pytest.param(_status(repository={"full_name": ATO.lower()}), id="status-repo-case-differs"),
])
def test_positive_control_an_answer_naming_what_was_asked_is_read(monkeypatch: pytest.MonkeyPatch, edit: object) -> None:
    assert _read(monkeypatch, edit) is None


def test_a_review_of_another_pull_never_makes_the_mission_approved(monkeypatch: pytest.MonkeyPatch,
                                                                    tmp_path: Path) -> None:
    """The reviewer's case end to end: with an allow-listed reviewer the stage must not say approved."""
    monkeypatch.setenv("TAO_DELIVERY_HUMAN_REVIEWERS", FAKE_REVIEWER)
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    _plant_state(st)
    _world(st)
    st.gh[REVIEWS] = [{**REVIEW, "pull_request_url": f"https://api.github.com/repos/Other/repo/pulls/8?redirect={BASE}/pulls/5"}]
    out = run(st)
    record = json.loads(Path(st.path).read_text(encoding="utf-8"))["missions"]["RA-1"]
    assert record["stage"] != "approval_wait" and record["reviewed_head_sha"] is None, record
    assert "RA-1" in out["not_refreshed_ids"]


# ---- the design rule: every part asked is compared exactly or carries a written reason ----

EXACT_KINDS = {"sha", "int", "repo", "text", "pull_url"}


def test_every_part_asked_is_compared_or_has_a_written_reason() -> None:
    for name, row in df.IDENTITY.items():
        asked, unchecked = set(row["asked"]), row.get("unchecked", {})
        compared = {part for _, parts, _ in row["checks"] for part in parts}
        assert len(row["asked"]) == len(asked) and asked, name
        assert compared | set(unchecked) == asked, (name, "a part asked is neither compared nor explained")
        assert not compared & set(unchecked), (name, "a part is both compared and explained away")
        assert all(isinstance(why, str) and len(why) > 40 for why in unchecked.values()), name


def test_every_github_row_asks_for_its_repository() -> None:
    github = {name for name, row in df.IDENTITY.items() if row["reader"] not in ("fetch_missions", "vercel_latest_ready")}
    assert github == {"pulls_list", "pull", "commit", "check_run", "status", "review", "compare"}
    for name in github:
        assert "repo" in df.IDENTITY[name]["asked"], name
    compared = {name for name in github if any("repo" in parts for _, parts, _ in df.IDENTITY[name]["checks"])}
    assert compared == {"pulls_list", "pull", "status", "review"}  # the answers GitHub documents a repository name for


def test_the_kinds_are_a_closed_list_of_exact_comparisons() -> None:
    assert set(df._KINDS) == EXACT_KINDS  # a new kind is reviewed here before it can be used
    assert {kind for row in df.IDENTITY.values() for _, _, kind in row["checks"]} <= EXACT_KINDS


@pytest.mark.parametrize("kind,value,wants,ok", [
    ("repo", "CleanExpo/ATO", ("cleanexpo/ato",), True),
    ("repo", "CleanExpo/ATO2", ("CleanExpo/ATO",), False),
    ("repo", "xCleanExpo/ATO", ("CleanExpo/ATO",), False),
    ("repo", f"CleanExpo/{KELVIN}TO", ("CleanExpo/kTO",), False),
    ("repo", "", ("",), False),
    ("text", "abc", ("abc",), True),
    ("text", "abc ", ("abc",), False),
    ("text", "ABC", ("abc",), False),
    ("int", 5, (5,), True),
    ("int", True, (1,), False),
    ("int", 5.0, (5,), False),
    ("int", "5", (5,), False),
    ("sha", "A" * 40, ("a" * 40,), True),
    ("sha", "a" * 40 + "0", ("a" * 40,), False),
    ("sha", "a" * 39, ("a" * 40,), False),
    ("pull_url", "https://api.github.com/repos/a/b/pulls/5", ("a/b", 5), True),
    ("pull_url", "https://api.github.com/repos/a/b/pulls/5", ("a/b", "5"), False),
    ("pull_url", "https://api.github.com/repos/a/b/pulls/5", ("a/b", True), False),
    ("pull_url", "https://api.github.com/repos/a/b/pulls/50", ("a/b", 5), False),
    ("pull_url", "https://api.github.com/repos/a/b/pulls/5", (None, 5), False),
    ("pull_url", f"https://api.github.com/repos/a/{KELVIN}/pulls/5", ("a/k", 5), False),
    ("pull_url", "https://api.github.com/repos/a/k/pulls/5", ("a/K", 5), True),
])
def test_each_kind_is_exact(kind: str, value: object, wants: tuple, ok: bool) -> None:
    assert bool(df._KINDS[kind](value, *wants)) is ok


def test_a_row_cannot_be_applied_without_every_part_asked() -> None:
    good = {"number": 5, "base": {"repo": {"full_name": ATO}}}
    assert df.identity_mismatch("pull", good, repo=ATO, number=5) is None
    with pytest.raises(TypeError):
        df.identity_mismatch("pull", good, number=5)  # the repository was not passed
    with pytest.raises(TypeError):
        df.identity_mismatch("pull", good, repo=ATO, number=5, extra=1)


# ---- round 8 warning: a repo record's live_unconfirmed is a commit SHA or null, never any text ----

def _repo_state(value: object) -> dict:
    from _delivery_stored_support import planted, stored
    rid = f"repo:{ATO}"
    return planted({rid: stored({"id": rid, "kind": "repo", "live_source": "live_unconfirmed", "live_unconfirmed": value})})


@pytest.mark.parametrize("value,sound", [(None, True), (SHA_A, True), ("verified-ok", False), (SHA_A.upper(), False),
                                         (SHA_A + "0", False), (5, False), ("", False)])
def test_a_repo_records_unconfirmed_commit_is_a_sha_or_null(value: object, sound: bool) -> None:
    from app.server import delivery_reconcile_schema as schema
    assert (schema.problems(_repo_state(value)) == []) is sound


# ---- pre-screen of 40ee8b24: three warnings of the same kind, closed by the same rule ----

EXPLAINED = {"commit": {"repo"}, "check_run": {"repo"}, "compare": {"repo", "head"}, "vercel": {"project", "team"}}


def test_only_these_parts_are_explained_instead_of_compared() -> None:
    """A part may not be moved to ``unchecked`` by writing a long enough reason: the list is reviewed here."""
    assert {name: set(row["unchecked"]) for name, row in df.IDENTITY.items() if row.get("unchecked")} == EXPLAINED


def _no_user_key(path: str, index: int | None):  # noqa: ANN202
    def edit(answers: dict) -> None:
        item = answers[path] if index is None else answers[path][index]
        item.update(item.pop("user"))  # login and type at the top level, where no documented answer has them
    return edit


@pytest.mark.parametrize("edit,reason", [
    pytest.param(_no_user_key(REVIEWS, 0), "malformed_review", id="review"),
    pytest.param(_no_user_key(f"{BASE}/pulls/5", None), "malformed_pull", id="pull"),
])
def test_an_answer_with_no_user_key_is_cut_whatever_else_it_carries(monkeypatch: pytest.MonkeyPatch, edit: object,
                                                                    reason: str) -> None:
    assert _read(monkeypatch, edit) == reason


def test_a_repository_name_that_is_not_ascii_is_never_in_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    lookalike = f"CleanExpo/s{KELVIN}ills-library"  # lower-cases to an allowed name
    allowed = frozenset({"cleanexpo/skills-library"})
    assert lookalike.lower() in allowed
    assert dc.in_scope([(lookalike, 5), ("CleanExpo/Skills-Library", 6)], allowed) == ([("CleanExpo/Skills-Library", 6)], 1)
    st = install_fakes(monkeypatch)
    with pytest.raises(dc.Unknown) as refused:
        dg._get(lookalike, "/pulls/5", dc.Tick(allowed=allowed))
    assert refused.value.reason == "out_of_scope" and st.github == []
