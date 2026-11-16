"""RA-8100: Cannot-verify label for repos with no provable live source."""
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.server.delivery_closure import Snapshot, Stage, assess, finding_key

NOW = datetime(2026, 11, 15, 0, 30, tzinfo=timezone.utc)
HEAD = "a" * 40
MERGE = "b" * 40


def snap(**changes: object) -> Snapshot:
    base = Snapshot(
        issue_id="RA-8100", project_id="unite-mission", stage=Stage.MERGED,
        stage_since=NOW - timedelta(hours=1), owner="PC Worker",
        acceptance_passed=True, tests_passed=True, pr_head_sha=HEAD,
        reviewed_head_sha=HEAD, authorised_head_sha=HEAD, merge_sha=MERGE,
        deployed_sha=None, verified_sha=None,
    )
    return replace(base, **changes)


@pytest.mark.parametrize("stage", [Stage.MERGED, Stage.DEPLOYING])
def test_g1_cannot_verify_label_never_ages(stage: Stage) -> None:
    keys = set()
    for hours in (1, 5, 30):
        item = snap(stage=stage, stage_since=NOW - timedelta(hours=hours),
                    live_source_provable=False)
        found = assess(item, NOW)
        assert len(found) == 1
        f = found[0]
        assert f.code == "LIVE_CANNOT_VERIFY"
        assert f.severity == "info"
        assert f.next_owner == "PC Worker"
        assert f.key == finding_key("RA-8100", stage.value, HEAD, "LIVE_CANNOT_VERIFY")
        keys.add(f.key)
    assert len(keys) == 1


def test_g1b_label_does_not_hide_a_verified_release() -> None:
    item = snap(deployed_sha=MERGE, verified_sha=MERGE, live_source_provable=False)
    assert [f.code for f in assess(item, NOW)] == ["CHECK_ACCEPTANCE"]


def test_g2_provable_source_still_ages() -> None:
    old = assess(snap(stage_since=NOW - timedelta(hours=30),
                      live_source_provable=True), NOW)
    assert [f.code for f in old] == ["DEPLOY_UNVERIFIED_24H"]
    assert old[0].severity == "founder"
    mid = assess(snap(stage_since=NOW - timedelta(hours=5),
                      live_source_provable=True), NOW)
    assert [f.code for f in mid] == ["DEPLOY_UNVERIFIED"]


@pytest.mark.parametrize("stage", list(Stage))
def test_g4_default_equals_provable_true(stage: Stage) -> None:
    for hours in (0, 2, 5, 30):
        kw = dict(stage=stage, stage_since=NOW - timedelta(hours=hours))
        assert assess(snap(**kw), NOW) == assess(snap(live_source_provable=True, **kw), NOW)
    assert snap().live_source_provable is True


def test_k1_finding_key_is_the_one_owner_of_the_formula() -> None:
    item = snap(owner=None, stage=Stage.REVIEW_WAIT)
    f = assess(item, NOW)[0]
    assert f.code == "UNOWNED"
    assert f.key == finding_key("RA-8100", "review_wait", HEAD, "UNOWNED")
    expected = hashlib.sha256(b"RA-8100|review_wait|" + HEAD.encode() + b"|UNOWNED").hexdigest()[:24]
    assert f.key == expected
    assert finding_key("X", "merged", None, "C") == hashlib.sha256(b"X|merged||C").hexdigest()[:24]
