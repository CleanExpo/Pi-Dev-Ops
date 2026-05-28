"""Tests for swarm.intake.handoff — G2 authority + idempotent 5-step ship."""
from __future__ import annotations

from dataclasses import replace

import pytest

from swarm.github_tools import GhRepo, PullRequestResult
from swarm.intake.handoff import (
    CreatedLinearIssue,
    HandoffRequest,
    HandoffState,
    LinearIssuePayload,
    NotificationPayload,
    PartnerBot,
    ProjectForHandoff,
    SpmAssessmentForHandoff,
    branch_name_for,
    broadcast_payloads,
    check_handoff_authority,
    execute_handoff,
    linear_payload_for,
    plan_handoff,
    pr_body_for,
    pr_title_for,
    slugify,
)


# ============================================================
# Stub clients
# ============================================================

class StubGh:
    def __init__(self, *, create_branch_fails: bool = False,
                 open_pr_fails: bool = False,
                 pr_url: str = "https://github.com/CleanExpo/Unite-Group/pull/42"):
        self.branches_created: list[tuple[str, str, str]] = []
        self.prs_opened: list[dict] = []
        self._create_branch_fails = create_branch_fails
        self._open_pr_fails = open_pr_fails
        self._pr_url = pr_url

    def create_branch(self, *, repo, base, new_branch):
        if self._create_branch_fails:
            raise RuntimeError("simulated branch failure")
        self.branches_created.append((repo.full_name, base, new_branch))

    def open_pr(self, *, repo, head, base, title, body):
        if self._open_pr_fails:
            raise RuntimeError("simulated PR failure")
        self.prs_opened.append({
            "repo": repo.full_name, "head": head, "base": base,
            "title": title, "body": body,
        })
        number = int(self._pr_url.rstrip("/").rsplit("/", 1)[-1])
        return PullRequestResult(url=self._pr_url, number=number)


class StubLinear:
    def __init__(self, *, fails: bool = False,
                 url: str = "https://linear.app/unite/issue/UG-101"):
        self.saved: list[LinearIssuePayload] = []
        self._fails = fails
        self._url = url

    def save_issue(self, payload):
        if self._fails:
            raise RuntimeError("simulated linear failure")
        self.saved.append(payload)
        return CreatedLinearIssue(id="UG-101", url=self._url)


class StubBroadcaster:
    def __init__(self):
        self.sent: list[tuple[str, NotificationPayload]] = []

    def send(self, *, partner_id, payload):
        self.sent.append((partner_id, payload))


# ============================================================
# Fixtures
# ============================================================

def _project(**overrides):
    base = dict(
        project_id="p1",
        workspace_slug="unite-group",
        name="Synthex Brand Refresh",
        slug="synthex-brand-refresh",
        owner_partner_id="phill",
        approval_policy="creator_only",
        github_repo="CleanExpo/Unite-Group",
        status="ready_for_production",
        description="Refresh the brand for spring launch.",
    )
    base.update(overrides)
    return ProjectForHandoff(**base)


def _spm():
    return SpmAssessmentForHandoff(
        summary="Brand refresh scoped, framework picked, success metrics defined.",
        open_questions=("Final colour palette sign-off?",),
        rationale="Three rounds of board input converged on scope.",
    )


def _bots():
    return [
        PartnerBot(partner_id="phill",  chat_id="100", display_name="Phill"),
        PartnerBot(partner_id="duncan", chat_id="200", display_name="Duncan"),
        PartnerBot(partner_id="toby",   chat_id="300", display_name="Toby"),
    ]


def _request(**proj_overrides):
    return HandoffRequest(
        project=_project(**proj_overrides),
        requesting_partner_id="phill",  # creator
        spm_assessment=_spm(),
    )


# ============================================================
# G2 — Authority gate
# ============================================================

class TestAuthorityGate:
    def test_creator_allowed_under_creator_only(self):
        check = check_handoff_authority(_project(), "phill")
        assert check.allowed is True

    def test_non_creator_denied_under_creator_only(self):
        check = check_handoff_authority(_project(), "duncan")
        assert check.allowed is False
        assert "creator-only" in check.reason

    def test_majority_policy_explicitly_denies(self):
        check = check_handoff_authority(
            _project(approval_policy="majority"), "phill",
        )
        assert check.allowed is False
        assert "not implemented" in check.reason

    def test_custom_policy_explicitly_denies(self):
        check = check_handoff_authority(
            _project(approval_policy="custom"), "phill",
        )
        assert check.allowed is False

    def test_execute_handoff_refuses_non_creator_with_no_side_effects(self):
        gh, linear, bc = StubGh(), StubLinear(), StubBroadcaster()
        request = HandoffRequest(
            project=_project(),
            requesting_partner_id="duncan",  # not the creator
            spm_assessment=_spm(),
        )
        state = execute_handoff(
            request, HandoffState(), _bots(),
            gh=gh, linear=linear, broadcaster=bc,
            linear_team_id="team-1", linear_project_id="lp-1",
        )
        assert state.status == "failed"
        assert "authority" in (state.error_message or "")
        assert gh.branches_created == []
        assert gh.prs_opened == []
        assert linear.saved == []
        assert bc.sent == []


# ============================================================
# Pure helpers
# ============================================================

class TestPureHelpers:
    def test_slugify(self):
        assert slugify("Synthex Brand Refresh") == "synthex-brand-refresh"
        assert slugify("  Foo!! Bar??  ") == "foo-bar"
        assert slugify("---") == ""

    def test_branch_name_uses_project_slug(self):
        assert branch_name_for(_project()) == "feat/synthex-brand-refresh"

    def test_branch_name_falls_back_to_name_slug(self):
        assert branch_name_for(_project(slug="")) == "feat/synthex-brand-refresh"

    def test_pr_title_human_readable(self):
        assert pr_title_for(_project()) == "feat: ship intake project — Synthex Brand Refresh"

    def test_pr_body_includes_creator_and_summary(self):
        body = pr_body_for(_project(), _spm(), requesting_partner_id="phill")
        assert "Synthex Brand Refresh" in body
        assert "phill" in body
        assert "Brand refresh scoped" in body
        assert "Approved by: phill" in body
        assert "Open questions" in body

    def test_pr_body_omits_questions_section_when_empty(self):
        spm = SpmAssessmentForHandoff(summary="ok", open_questions=())
        body = pr_body_for(_project(), spm, requesting_partner_id="phill")
        assert "Open questions" not in body

    def test_linear_payload_includes_description_and_questions(self):
        payload = linear_payload_for(
            _project(), _spm(),
            team_id="team-1", project_linear_id="lp-1",
        )
        assert payload.team_id == "team-1"
        assert payload.project_id == "lp-1"
        assert "Synthex Brand Refresh" in payload.title
        assert "spring launch" in payload.description
        assert "Open questions" in payload.description

    def test_broadcast_payloads_one_per_bot(self):
        bots = _bots()
        out = broadcast_payloads(_project(), bots,
                                 pr_url="https://x/pr/1",
                                 linear_url="https://l/issue/1")
        assert len(out) == 3
        for partner_id, payload in out:
            assert partner_id in {"phill", "duncan", "toby"}
            assert "Synthex Brand Refresh" in payload.text
            assert "https://x/pr/1" in payload.text
            assert "https://l/issue/1" in payload.text


# ============================================================
# plan_handoff — pure dry-run
# ============================================================

class TestPlanHandoff:
    def test_plan_does_not_touch_clients(self):
        plan = plan_handoff(
            _request(), _bots(),
            linear_team_id="team-1", linear_project_id="lp-1",
        )
        assert plan.branch_name == "feat/synthex-brand-refresh"
        assert plan.pr_title.startswith("feat: ship intake project")
        assert plan.linear_payload.team_id == "team-1"
        assert len(plan.broadcasts) == 3
        # placeholder links until real handoff fires
        for _, payload in plan.broadcasts:
            assert "(pending)" in payload.text


# ============================================================
# execute_handoff — happy path
# ============================================================

class TestExecuteHandoffHappyPath:
    def test_full_run_completes(self):
        gh, linear, bc = StubGh(), StubLinear(), StubBroadcaster()
        state = execute_handoff(
            _request(), HandoffState(), _bots(),
            gh=gh, linear=linear, broadcaster=bc,
            linear_team_id="team-1", linear_project_id="lp-1",
        )
        assert state.status == "complete"
        assert state.branch_name == "feat/synthex-brand-refresh"
        assert state.pr_url and state.pr_number
        assert state.linear_issue_id == "UG-101"
        assert state.linear_issue_url
        assert set(state.notified_partner_ids) == {"phill", "duncan", "toby"}
        # Side effects in the right order
        assert gh.branches_created == [
            ("CleanExpo/Unite-Group", "main", "feat/synthex-brand-refresh"),
        ]
        assert len(gh.prs_opened) == 1
        assert len(linear.saved) == 1
        assert len(bc.sent) == 3
        # Broadcast text references real URLs, not placeholders
        for _, payload in bc.sent:
            assert "(pending)" not in payload.text


# ============================================================
# Idempotency — resume from prior status
# ============================================================

class TestIdempotency:
    def test_resume_from_pr_opened_skips_branch_and_pr(self):
        gh, linear, bc = StubGh(), StubLinear(), StubBroadcaster()
        prior = HandoffState(
            handoff_id="h1",
            status="pr_opened",
            branch_name="feat/synthex-brand-refresh",
            pr_url="https://github.com/CleanExpo/Unite-Group/pull/42",
            pr_number=42,
        )
        state = execute_handoff(
            _request(), prior, _bots(),
            gh=gh, linear=linear, broadcaster=bc,
            linear_team_id="team-1", linear_project_id="lp-1",
        )
        assert state.status == "complete"
        # No re-branch, no re-PR
        assert gh.branches_created == []
        assert gh.prs_opened == []
        # But Linear + broadcast did fire
        assert len(linear.saved) == 1
        assert len(bc.sent) == 3

    def test_resume_from_notified_just_marks_complete(self):
        gh, linear, bc = StubGh(), StubLinear(), StubBroadcaster()
        prior = HandoffState(
            handoff_id="h1",
            status="notified",
            branch_name="feat/synthex-brand-refresh",
            pr_url="https://github.com/CleanExpo/Unite-Group/pull/42",
            pr_number=42,
            linear_issue_id="UG-101",
            linear_issue_url="https://linear.app/unite/issue/UG-101",
            notified_partner_ids=("phill", "duncan", "toby"),
        )
        state = execute_handoff(
            _request(), prior, _bots(),
            gh=gh, linear=linear, broadcaster=bc,
            linear_team_id="team-1", linear_project_id="lp-1",
        )
        assert state.status == "complete"
        assert gh.branches_created == []
        assert linear.saved == []
        assert bc.sent == []

    def test_partial_notify_resumes_remaining_partners(self):
        gh, linear, bc = StubGh(), StubLinear(), StubBroadcaster()
        prior = HandoffState(
            handoff_id="h1",
            status="linear_created",
            branch_name="feat/synthex-brand-refresh",
            pr_url="https://github.com/CleanExpo/Unite-Group/pull/42",
            pr_number=42,
            linear_issue_id="UG-101",
            linear_issue_url="https://linear.app/unite/issue/UG-101",
            notified_partner_ids=("phill",),  # only Phill was notified
        )
        state = execute_handoff(
            _request(), prior, _bots(),
            gh=gh, linear=linear, broadcaster=bc,
            linear_team_id="team-1", linear_project_id="lp-1",
        )
        assert state.status == "complete"
        # Only Duncan + Toby got notified this run
        sent_ids = [p for p, _ in bc.sent]
        assert set(sent_ids) == {"duncan", "toby"}
        assert set(state.notified_partner_ids) == {"phill", "duncan", "toby"}


# ============================================================
# Failure handling
# ============================================================

class TestFailureHandling:
    def test_branch_failure_records_error_no_pr(self):
        gh = StubGh(create_branch_fails=True)
        linear, bc = StubLinear(), StubBroadcaster()
        state = execute_handoff(
            _request(), HandoffState(), _bots(),
            gh=gh, linear=linear, broadcaster=bc,
            linear_team_id="team-1", linear_project_id="lp-1",
        )
        assert state.status == "failed"
        assert "branch" in (state.error_message or "").lower()
        assert gh.prs_opened == []
        assert linear.saved == []
        assert bc.sent == []

    def test_linear_failure_keeps_pr_state_for_retry(self):
        gh = StubGh()
        linear = StubLinear(fails=True)
        bc = StubBroadcaster()
        state = execute_handoff(
            _request(), HandoffState(), _bots(),
            gh=gh, linear=linear, broadcaster=bc,
            linear_team_id="team-1", linear_project_id="lp-1",
        )
        assert state.status == "failed"
        # PR already opened — saved to state for resume
        assert state.branch_name == "feat/synthex-brand-refresh"
        assert state.pr_url is not None
        assert state.pr_number is not None
        assert state.linear_issue_id is None
        assert bc.sent == []


# ============================================================
# Repo parsing
# ============================================================

class TestGhRepoParse:
    def test_parse_valid(self):
        repo = GhRepo.parse("CleanExpo/Unite-Group")
        assert repo.owner == "CleanExpo"
        assert repo.name == "Unite-Group"
        assert repo.full_name == "CleanExpo/Unite-Group"

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            GhRepo.parse("just-a-name")
        with pytest.raises(ValueError):
            GhRepo.parse("/missing-owner")
        with pytest.raises(ValueError):
            GhRepo.parse("missing-name/")
