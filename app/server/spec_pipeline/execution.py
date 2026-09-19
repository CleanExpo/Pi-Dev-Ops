"""Execute an approved specification against one immutable delivery candidate."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .execution_evidence import persist_result, record_review, record_ship


@dataclass
class PipelineExecution:
    api: Any
    pipeline_id: str
    proposal: str
    issue_id: str | None
    trigger: str
    boardroom: Any
    spec: Any
    final_judge: Any
    stages: list[dict[str, Any]]
    base_sha: str = ""
    candidate_sha: str = ""
    candidate_tree: str = ""

    def blocked(self, stage: str, reason: str, *, status: str = "blocked"):
        self.stages.append({"stage": stage, "status": status, "reason": reason})
        label = {"boundary": "blocked — diff boundary", "review": "blocked — review"}.get(
            stage, f"{status} — {stage}"
        )
        self.api.linear_reporter.report(self.issue_id, label, reason)
        return persist_result(self, status, reason)

    def prepare_workspace(self):
        ws_root = Path(
            os.environ.get("TAO_WORKSPACE", "/tmp/pi-ceo-workspaces")
        ).resolve()
        self.workspace = str(ws_root / self.pipeline_id)
        if Path(self.workspace).exists():
            return self.blocked(
                "workspace",
                "Workspace already exists; preserve it and use a new pipeline ID",
            )
        try:
            ws_root.mkdir(parents=True, exist_ok=True)
            self.api._git(
                str(ws_root),
                "clone",
                "--no-hardlinks",
                "--",
                str(self.api.REPO_ROOT),
                self.workspace,
            )
            self.base_sha = self.api._git(self.workspace, "rev-parse", "HEAD")
            if not self.api._object_id(self.base_sha):
                return self.blocked("workspace", "Missing immutable base revision")
        except (RuntimeError, OSError) as exc:
            return self.blocked("workspace", str(exc))

    async def build(self):
        self.api.linear_reporter.report(
            self.issue_id, "build started", f"Workspace `{self.workspace}`. Goal: {self.spec.goal_command}"
        )
        try:
            self.loop_result = await self.api.run_until_done(
                goal=self.spec.goal_command,
                workspace=self.workspace,
                max_iters=int(os.environ.get("TAO_MAX_ITERS", "25")),
                judge_every_n_iters=1,
                timeout_per_iter_s=600,
                **self.api.resolve_planner_loop_kwargs(),
            )
        except Exception as exc:
            return self.blocked("build", f"Build loop failed ({type(exc).__name__})")
        self.api.persist.append_jsonl(
            self.pipeline_id,
            "05-build-loop.jsonl",
            {
                "done": self.loop_result.done,
                "reason": self.loop_result.reason,
                "iters": self.loop_result.iters,
                "cost_usd": self.loop_result.cost_usd,
            },
        )
        self.stages.append(
            {
                "stage": "build",
                "status": "ok" if self.loop_result.done is True else "incomplete",
                "reason": self.loop_result.reason,
            }
        )
        if self.loop_result.done is not True:
            return self.blocked("build", f"Build incomplete: {self.loop_result.reason}")

    def prepare_candidate(self):
        self.branch = f"pidev/auto-{self.pipeline_id[:8]}"
        try:
            self.api._git(self.workspace, "reset", "--soft", self.base_sha)
            self.api._git(self.workspace, "checkout", "-b", self.branch)
            self.api._git(self.workspace, "add", "-A")
            self.candidate_tree = self.api._git(self.workspace, "write-tree")
            if not self.api._object_id(self.candidate_tree):
                return self.blocked("candidate", "Missing immutable candidate tree")
        except RuntimeError as exc:
            return self.blocked("candidate", str(exc))

    def review_candidate(self):
        try:
            diff_boundary = self.api.scan_diff_boundary(self.workspace)
            if diff_boundary.tier != "ok":
                return self.blocked(
                    "boundary", f"Diff boundary did not pass: {diff_boundary.tier}"
                )
            oracles = self.api.run_oracles(self.workspace)
            self.oracles_passed = all(
                oracles.get(k) is True for k in ("import_ok", "pytest_ok", "tsc_ok")
            )
            if not self.oracles_passed:
                record_review(self, {"verdict": "BLOCKED"}, oracles)
                return self.blocked(
                    "review", "Required executable checks failed or were not observed"
                )
            self.review = self.api.run_review(self.workspace, oracles=oracles)
            self.review_packet = record_review(self, self.review.to_dict(), oracles)
            self.stages.append(
                {
                    "stage": "review",
                    "status": self.review.verdict,
                    "candidate_tree": self.candidate_tree,
                }
            )
            if self.review.verdict not in {"PASS", "PASS_WITH_WARNINGS"}:
                return self.blocked(
                    "review",
                    "; ".join(self.review.blockers)
                    or f"Review did not approve: {self.review.verdict}",
                )
        except Exception as exc:
            return self.blocked(
                "review", f"Required review failed ({type(exc).__name__})"
            )

    def commit_and_push(self):
        try:
            result = self.commit_candidate()
            if result is not None:
                return result
            self.review_packet["candidate_sha"] = self.candidate_sha
            self.api.persist.write_json(
                self.pipeline_id, "06-review-packet.json", self.review_packet
            )
            remote = os.environ.get(
                "GITHUB_REPO_URL", f"https://github.com/{self.api.DEFAULT_REPO}.git"
            )
            from app.server.session_phases import _git_clone_env

            self.api._git(self.workspace, "remote", "set-url", "origin", remote)
            self.api._git(
                self.workspace,
                "push",
                "-u",
                "origin",
                f"{self.candidate_sha}:refs/heads/{self.branch}",
                env=_git_clone_env(remote),
            )
        except RuntimeError as exc:
            return self.blocked("ship", str(exc), status="ship_blocked")

    def commit_candidate(self):
        self.api._git(self.workspace, "add", "-A")
        if (
            self.api._git(self.workspace, "write-tree") != self.candidate_tree
            or self.api._git(self.workspace, "rev-parse", "HEAD") != self.base_sha
        ):
            return self.blocked(
                "candidate",
                "Candidate changed during verification; rerun required checks",
            )
        self.api._git(
            self.workspace,
            "commit",
            "-m",
            f"Deliver the approved machine specification: {self.proposal[:72]}\n\n"
            "Confidence: high\nScope-risk: narrow\nTested: Required pipeline oracles and review",
        )
        self.candidate_sha = self.api._git(self.workspace, "rev-parse", "HEAD")
        if (
            not self.api._object_id(self.candidate_sha)
            or self.api._git(self.workspace, "rev-parse", "HEAD^{tree}")
            != self.candidate_tree
            or self.api._git(self.workspace, "status", "--porcelain")
        ):
            return self.blocked(
                "candidate",
                "Committed candidate differs from the verified tree or is dirty",
            )

    def publish(self):
        try:
            self.ship = self.api.open_pr_and_merge(
                repo=self.api.DEFAULT_REPO,
                branch=self.branch,
                candidate_sha=self.candidate_sha,
                title=f"feat(spec-pipeline): {self.proposal[:80]}",
                body=f"Machine spec pipeline `{self.pipeline_id}`\n\nTrigger: {self.trigger}\nIssue: {self.issue_id or 'n/a'}",
            )
        except Exception as exc:
            return self.blocked(
                "ship",
                f"PR delivery failed ({type(exc).__name__})",
                status="ship_blocked",
            )
        if not isinstance(self.ship, dict):
            return self.blocked(
                "ship", "Missing structured merge evidence", status="ship_blocked"
            )
        record_ship(self)

    def finish(self):
        self.api._log_machine_gate(
            self.pipeline_id,
            {
                "spec_exists": True,
                "plan_exists": True,
                "build_complete": True,
                "tests_passed": self.oracles_passed,
                "review_passed": self.review.verdict in ("PASS", "PASS_WITH_WARNINGS"),
                "shipped": self.merged,
            },
            float(self.final_judge.score),
        )
        status = "complete" if self.merged else "ship_blocked"
        reason = str(self.ship.get("reason") or self.ship.get("status", "unknown"))
        self.api.linear_reporter.report(
            self.issue_id,
            status,
            f"{self.ship.get('pr_url', '')} ({self.ship.get('status', '')})",
        )
        return persist_result(self, status, reason, self.ship.get("pr_url", ""))


async def execute(**context: Any) -> Any:
    from importlib import import_module

    execution = PipelineExecution(api=import_module(__package__), **context)
    result = execution.prepare_workspace()
    if result is not None:
        return result
    result = await execution.build()
    if result is not None:
        return result
    for stage in (
        execution.prepare_candidate,
        execution.review_candidate,
        execution.commit_and_push,
        execution.publish,
    ):
        result = stage()
        if result is not None:
            return result
    return execution.finish()
