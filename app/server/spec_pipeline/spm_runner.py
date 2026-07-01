"""SPM spec runner — 19-section spec from approved judge report."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .llm import complete
from .prebuild_judge import JudgeReport

log = logging.getLogger("pi-ceo.spec_pipeline.spm_runner")


@dataclass
class SpmSpec:
    markdown: str
    goal_command: str

    def to_dict(self) -> dict[str, Any]:
        return {"markdown": self.markdown, "goal_command": self.goal_command}


async def run_spm(proposal: str, judge_report: JudgeReport) -> SpmSpec:
    prompt = (
        "You are the Senior Project Manager. Produce a decision-grade spec.md "
        "with sections 1–19 (task, context, problem, outcome, scope, non-goals, "
        "existing capability, specialist board, judge challenge, solution, UX, "
        "technical, security, verification, stress tests, acceptance criteria, "
        "goal command, implementation sequence, handoff seed, recommendation).\n\n"
        f"Proposal:\n{proposal}\n\n"
        f"Judge report (approved):\n{judge_report.to_dict()}\n\n"
        "End with a line: GOAL_COMMAND: /goal <measurable completion condition>"
    )
    text, _ = await complete(prompt=prompt, role="spm_runner", max_tokens=6000)
    goal = "/goal implement the spec acceptance criteria"
    for line in text.splitlines():
        if line.strip().upper().startswith("GOAL_COMMAND:"):
            goal = line.split(":", 1)[1].strip()
            break
    return SpmSpec(markdown=text, goal_command=goal)
