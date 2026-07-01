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
    return _parse_spm_output(text)


async def run_spm_gap_resolution(
    proposal: str,
    judge_report: JudgeReport,
    *,
    board_memo: str,
    gap_resolutions: list[dict[str, str]],
) -> SpmSpec:
    """SPM pass that answers judge questions using ceo-board liaison output."""
    res_lines = "\n".join(
        f"- {r.get('gap', '')}: {r.get('resolution', '')}" for r in gap_resolutions
    ) or "(none)"
    prompt = (
        "You are the Senior Project Manager closing judge gaps before build.\n"
        "Produce an amendment packet (not full 19-section spec yet) with:\n"
        "1. REFINED_PROPOSAL — single paragraph the judge can re-score\n"
        "2. GAP_ANSWERS — numbered answers to every judge gap\n"
        "3. SCOPE_LOCK — files/modules in scope, explicit non-goals\n"
        "4. VERIFICATION — how each gap answer will be proven in CI/manual path\n"
        "5. GOAL_COMMAND line at end\n\n"
        f"Proposal:\n{proposal}\n\n"
        f"Judge score: {judge_report.score} gaps: {judge_report.gaps}\n\n"
        f"CEO-board memo:\n{board_memo[:5000]}\n\n"
        f"Gap resolutions:\n{res_lines}\n\n"
        "End with: GOAL_COMMAND: /goal <measurable completion condition>"
    )
    text, _ = await complete(prompt=prompt, role="spm_gap_resolution", max_tokens=4000)
    return _parse_spm_output(text)


def _parse_spm_output(text: str) -> SpmSpec:
    goal = "/goal implement the spec acceptance criteria"
    refined = ""
    for line in text.splitlines():
        upper = line.strip().upper()
        if upper.startswith("GOAL_COMMAND:"):
            goal = line.split(":", 1)[1].strip()
        elif upper.startswith("REFINED_PROPOSAL:"):
            refined = line.split(":", 1)[1].strip()
    markdown = text
    if refined:
        markdown = f"## Refined proposal\n{refined}\n\n{text}"
    return SpmSpec(markdown=markdown, goal_command=goal)


def extract_refined_proposal(spm: SpmSpec, fallback: str) -> str:
    """Pull refined proposal paragraph from SPM gap-resolution output."""
    for line in spm.markdown.splitlines():
        if line.strip().upper().startswith("REFINED_PROPOSAL:"):
            return line.split(":", 1)[1].strip()
    if spm.markdown.startswith("## Refined proposal"):
        parts = spm.markdown.split("\n\n", 2)
        if len(parts) >= 2:
            return parts[0].replace("## Refined proposal", "").strip() or parts[1][:500]
    return fallback
