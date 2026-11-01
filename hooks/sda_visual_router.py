#!/usr/bin/env python3
"""Lightweight existing UserPromptSubmit hook: route design work to real SDA QA.

No network calls, generated files, model credits, or blanket stop hooks.
Only emits extra context for design/visual/media prompts.
"""
import json
import re
import sys

PATTERN = re.compile(
    r"\b(?:SDA|UX|UI|visual|design|website|webpage|landing page|"
    r"business card|animation|motion design|video|render|playwright|"
    r"brand film|prototype|interface|screenshots?)\b", re.I
)
CONTEXT = (
    "SDA VISUAL QUALITY REQUIREMENT: existing visual-qa and design-approve "
    "skills on this MacBook now require real Playwright Chromium mobile/tablet/"
    "desktop screenshots, actual-video frame inspection when relevant, "
    "frozen SHA-256 baselines, substantive visual critique and a different "
    "independent challenger. Do NOT equate a green technical test with polished "
    "design. Set PI_DEV_OPS_ROOT to the ABSOLUTE path of the clean, exact-SHA "
    "reviewed Pi-Dev-Ops checkout; verify git -C \"$PI_DEV_OPS_ROOT\" "
    "rev-parse HEAD equals the signed independent review receipt before any "
    "execution. Missing path, dirty source or SHA mismatch is HOLD. Run "
    "python3 \"$PI_DEV_OPS_ROOT/skills/visual-qa/scripts/sda_evidence_gate.py\" "
    "<evidence-dir>/SDA_EVIDENCE_MANIFEST.json --scope-record "
    "<independent-scope.json>. For proposed commercial release also include "
    "--release --baseline-record <separate-frozen-approval.json>; "
    "HOLD without signed release gate, real approvals, verified rights, "
    "authenticated tenant authority and exact-version creative acceptance. "
    "Do not use an unverified installed skill copy or treat technical green "
    "as creative acceptance."
)


def route(payload):
    prompt = payload.get("prompt", payload.get("user_prompt", ""))
    if isinstance(prompt, str) and PATTERN.search(prompt[:12000]):
        return {"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": CONTEXT}}
    return None


def main():
    try:
        data = json.load(sys.stdin)
        if isinstance(data, dict):
            result = route(data)
            if result:
                print(json.dumps(result))
    except (ValueError, OSError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
