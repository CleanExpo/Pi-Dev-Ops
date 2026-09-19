"""Persist candidate-bound specification pipeline evidence."""


def persist_result(execution, status, reason, pr_url=""):
    api = execution.api
    common = {
        "judge_score": 100,
        "boardroom_decision": execution.boardroom.decision,
        "candidate_sha": execution.candidate_sha,
        "stages": execution.stages,
    }
    api._write_handoff(
        execution.pipeline_id,
        status=status.upper(),
        proposal=execution.proposal,
        reason=reason,
        extra={"pickup": pr_url} if pr_url else {},
    )
    api._persist_meta(
        execution.pipeline_id,
        status=status,
        proposal=execution.proposal,
        reason=reason,
        base_sha=execution.base_sha,
        candidate_tree=execution.candidate_tree,
        pr_url=pr_url,
        **common,
    )
    return api.PipelineResult(
        execution.pipeline_id, status, reason, pr_url=pr_url, **common
    )


def record_review(execution, review, oracles):
    packet = {
        **review,
        "oracles": oracles,
        "base_sha": execution.base_sha,
        "candidate_tree": execution.candidate_tree,
    }
    execution.api.persist.write_json(
        execution.pipeline_id, "06-review-packet.json", packet
    )
    return packet


def record_ship(self):
    self.merged = (
        self.ship.get("status") == "merged"
        and self.ship.get("candidate_sha") == self.candidate_sha
        and self.api._object_id(self.ship.get("merge_sha", ""))
        and bool(self.ship.get("pr_url"))
    )
    if self.ship.get("status") == "merged" and (not self.merged):
        self.ship = {
            **self.ship,
            "status": "invalid_receipt",
            "reason": "Missing matching candidate or actual merge evidence",
        }
    self.ship = {
        **self.ship,
        "base_sha": self.base_sha,
        "candidate_tree": self.candidate_tree,
        "pushed_sha": self.candidate_sha,
    }
    self.api.persist.write_json(self.pipeline_id, "07-ship-result.json", self.ship)
    self.api.linear_reporter.report(
        self.issue_id,
        "PR opened",
        f"{self.ship.get('pr_url') or 'no URL'} — status {self.ship.get('status')}",
    )
    self.stages.append(
        {
            "stage": "ship",
            "status": self.ship.get("status", "unknown"),
            "candidate_sha": self.candidate_sha,
        }
    )
