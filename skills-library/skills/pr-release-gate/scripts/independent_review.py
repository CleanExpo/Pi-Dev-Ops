#!/usr/bin/env python3
"""Run the pr-release-gate independent review across ANY available non-Claude vendor.

WHY THIS EXISTS — read before changing anything here.

The release law requires a review by an agent that is not the implementing agent.
For months the only wired lane was `codex`, so every time OpenAI's quota window
closed, work stopped and a session reported "blocked on codex quota" — while a
live Gemini key and an uncapped OpenRouter key sat unused on the same machine.
That happened repeatedly. The founder's instruction on 19/08/2026 was explicit:
there is more than codex; use it, and hard-code it so this stops recurring.

Two failure modes are designed out here, both observed:

1. ONE VENDOR IS NOT A LANE. Lanes are tried in order and the FIRST that returns
   a valid report wins. Exhausting one vendor is not a stop; exhausting ALL of
   them is, and only then.

2. AN EXIT CODE IS NOT A VERDICT. `codex exec` EXITS 0 when it hits its usage
   limit and writes no report. A session that trusted the status would have
   recorded a review that never happened as gate evidence. Every lane here is
   judged on THE REPORT FILE, never on the process status.

Credentials are resolved from the estate's real locations, in priority order, and
are never printed. `~/.hermes/.env` is the estate's densest secret store (~26
credentials) and is checked FIRST for anything that seems missing — a previous
probe declared OpenRouter absent estate-wide because it checked shell env and
~/.config but never that file.

    usage: independent_review.py --brief <path> --base <sha> --head <sha>
                                [--out <path>] [--repo <dir>] [--lane <name>]
                                [--list-lanes]

Exit 0 only when a schema-1 report exists on disk. Exit 2 when every lane failed,
with the per-lane reason printed so the blocker is named rather than guessed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# The registry sits beside this file. Insert its directory explicitly rather than relying
# on sys.path[0]: that holds only when this script is the entry point, and pr_release_gate
# imports it as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lane_registry  # noqa: E402 - path must be set before this import

HOME = Path.home()

# ── credential resolution ───────────────────────────────────────────────────
# Ordered. First hit wins. Never logged, never echoed, never passed on argv.
CREDENTIAL_SOURCES = {
    "OPENROUTER_API_KEY": [
        HOME / ".hermes/.env",              # the estate's densest secret store
        HOME / ".claude/.env",
        HOME / "Unite-Group/.env.local",
        HOME / "Synthex/.env.local",
    ],
    "GEMINI_API_KEY": [
        HOME / "CARSI/.env.local",          # verified live 19/08/2026
        HOME / ".hermes/.env",
        HOME / "Unite-Group/.env.local",    # NOTE: known-dead key lives here
        HOME / "RestoreAssist/.env.local",
    ],
}


def resolve_secret(name: str) -> str | None:
    """Environment first, then the known files. Returns None rather than raising."""
    val = os.environ.get(name)
    if val and val.strip():
        return val.strip()
    pattern = re.compile(rf"^{re.escape(name)}=(.+)$")
    for path in CREDENTIAL_SOURCES.get(name, []):
        try:
            for line in path.read_text().splitlines():
                m = pattern.match(line.strip())
                if m:
                    candidate = m.group(1).strip().strip('"').strip("'")
                    # Skip obvious placeholders rather than failing downstream.
                    if candidate and not candidate.lower().startswith(("your_", "your-", "<", "sk-or-v1-xxx")):
                        return candidate
        except (OSError, UnicodeDecodeError):
            continue
    return None


# ── report validation — the ONLY thing that counts as success ───────────────
# The eight obligations owned by REVIEW_CHECKLIST in pr_release_gate.py. Spelled
# here so the runner rejects a non-conforming PASS BEFORE the recorder does, rather
# than after a round has been spent. Schema 1's `reviewed_dimensions` was a fixed
# seven-string list validated against a constant, so a reviewer discharged it by
# copying the example out of the schema doc; five consecutive rounds on one branch
# declared byte-identical dimensions while returning 3, 2, 1, 11 and 11 findings.
CHECKLIST_IDS = frozenset({
    "coverage-ledger", "plan-conformance", "weakened-checks", "mutation-control",
    "guard-falsification", "clean-environment-suite", "blast-radius",
    "outbound-actions",
})
CHECKLIST_VERDICTS = frozenset({"PASS", "N/A"})


def _check_schema2_pass(d: dict) -> tuple[bool, str]:
    """A PASS must be an enumerable checklist plus a coverage ledger.

    Mirrors pr_release_gate.REVIEW_SCHEMA: only a PASS — the verdict that releases
    code — needs schema 2. A schema-1 FAIL still stands, because its payload is its
    findings, so a drain loop already in flight keeps working.
    """
    if d.get("schema") != 2:
        return False, (f"verdict=PASS needs schema 2 (got {d.get('schema')!r}). A "
                       "releasing verdict carries `checklist` and `coverage`.")
    items = d.get("checklist")
    if not isinstance(items, list) or not items:
        return False, "schema 2 PASS has no `checklist` list"
    seen = {}
    for entry in items:
        if not isinstance(entry, dict):
            return False, f"checklist entry is not an object: {entry!r}"
        cid = str(entry.get("id", "")).strip()
        verdict = str(entry.get("verdict", "")).strip()
        if verdict not in CHECKLIST_VERDICTS:
            return False, (f"checklist item {cid!r} verdict {verdict!r} is not PASS or "
                           "N/A — a real failure is a blocking finding, not a checklist FAIL")
        if not str(entry.get("evidence", "")).strip():
            return False, f"checklist item {cid!r} has no evidence"
        if verdict == "N/A" and not str(entry.get("reason", "")).strip():
            return False, f"checklist item {cid!r} is N/A without a reason"
        seen[cid] = verdict
    missing = sorted(CHECKLIST_IDS - set(seen))
    unknown = sorted(set(seen) - CHECKLIST_IDS)
    if missing:
        return False, f"checklist omits required items: {missing}"
    if unknown:
        return False, f"checklist carries unknown items: {unknown}"
    cov = d.get("coverage")
    if not isinstance(cov, dict):
        return False, "schema 2 PASS has no `coverage` object"
    if not isinstance(cov.get("reviewed"), list):
        return False, "`coverage.reviewed` must be a list"
    skipped = cov.get("not_reviewed") or []
    if not isinstance(skipped, list):
        return False, "`coverage.not_reviewed` must be a list"
    for entry in skipped:
        if not isinstance(entry, dict):
            return False, f"not_reviewed entry is not an object: {entry!r}"
        if not str(entry.get("path", "")).strip():
            return False, "a not_reviewed entry has no path"
        if not str(entry.get("reason", "")).strip():
            return False, f"not_reviewed {entry.get('path')!r} carries no reason"
    return True, ""


def validate_report(path: Path, base: str, head: str, reviewer: str,
                    coverage: dict | None = None) -> tuple[bool, str]:
    if not path.exists():
        return False, "no report file was written"
    try:
        d = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"report is not readable JSON: {exc}"
    if d.get("schema") not in (1, 2):
        return False, f"schema must be 1 or 2, got {d.get('schema')!r}"
    if d.get("base_sha") != base or d.get("head_sha") != head:
        return False, (f"report is not bound to this diff: base={d.get('base_sha')!r} "
                       f"head={d.get('head_sha')!r}")
    if str(d.get("reviewer_agent", "")).strip().lower() == "claude":
        return False, "reviewer_agent is claude — that is not an independent review"
    if d.get("verdict") not in ("PASS", "FAIL"):
        return False, f"verdict must be PASS or FAIL, got {d.get('verdict')!r}"
    if d["verdict"] == "PASS":
        ok, why = _check_schema2_pass(d)
        if not ok:
            return False, why
    # A FAIL that names no blocking finding is not a review — it is a model
    # declining to answer in the shape of a verdict. Observed 19/08/2026: three
    # lanes in a row returned exactly {"verdict":"FAIL","blocking_findings":[]}
    # because they were never shown the diff, and the runner returned the first
    # one as the WINNING lane. That records a review that never happened, which is
    # the same defect as trusting codex's exit code, one level up. Falling through
    # to the next lane is correct; a real FAIL always cites what blocks.
    if d["verdict"] == "FAIL" and not (d.get("blocking_findings") or []):
        return False, ("verdict=FAIL with zero blocking_findings — a fail that names "
                       "no blocker is not a review; treating this lane as failed")
    # A PASS ON A TRUNCATED DIFF IS NOT A PASS. Exactly symmetric with the FAIL rule
    # above: it records a review of the whole that examined only a part. Measured
    # 21/08/2026 — nine reviews at 40-42% coverage, in every one of which the SQL
    # destined for production fell off the tail; then a tenth at 36.9% that PASSED
    # without receiving any of the four files it was commissioned to judge. A FAIL on a
    # truncated diff still stands; only the PASS is refused, because only the PASS is a
    # claim about what was not shown. Scope the pass with --paths.
    if coverage and coverage.get("truncated") and d["verdict"] == "PASS":
        pct = coverage["shown_chars"] / coverage["total_chars"] * 100
        unseen = coverage.get("unseen_files") or []
        more = f" (+{len(unseen) - 6} more)" if len(unseen) > 6 else ""
        return False, (
            f"verdict=PASS on a TRUNCATED diff — the reviewer saw "
            f"{coverage['shown_chars']} of {coverage['total_chars']} chars ({pct:.0f}%) "
            f"and never read: {', '.join(unseen[:6])}{more}. A PASS cannot certify what "
            f"was not shown; refusing to record it. Scope the pass with --paths.")
    if coverage:
        # Travels with the report so a receipt can never claim more than the review
        # examined, and so a scoped pass is legible as scoped.
        d["diff_coverage"] = coverage
        path.write_text(json.dumps(d, indent=2))
    scope = f" scope={' '.join(coverage['scope_paths'])}" if (
        coverage and coverage.get("scope_paths")) else ""
    return True, (f"verdict={d['verdict']} "
                  f"blocking={len(d.get('blocking_findings') or [])}{scope}")


# ── lane 0: cursor-agent CLI ────────────────────────────────────────────────
# Added 17/09/2026. Cursor is the lane that has actually produced gate-grade reviews
# in September 2026: it runs in the review worktree with a shell, so it can execute
# mutants, which the API-only lanes cannot. Like codex, it writes
# ./reviewer-report.json itself, and like codex it is judged on that file only.
CURSOR_TIMEOUT_S = 2400


def _shell_run_facts(base: str, head: str, reviewer: str) -> str:
    """The run's facts, appended LAST so they override the brief (25/09/2026: a brief whose
    top still carried round 1's base cost two reports, and one naming an --out path it never
    gave cost a Codex round). The API lanes get the same from _report_instruction."""
    return f"""

════════ RUN FACTS — THESE OVERRIDE ANY SHA, AGENT OR REPORT PATH ABOVE ════════
base_sha: {base}
head_sha: {head}
reviewer_agent: {reviewer}
Write the report as `reviewer-report.json` at the root of your current working directory.
The runner collects it from there. There is no other location; do not ask for one.
Any other base, head, reviewer name or report path in the brief above is stale.
"""


def lane_cursor(brief: str, workdir: Path, out: Path, base: str, head: str) -> tuple[bool, str]:
    exe = which("cursor-agent") or (
        str(Path.home() / ".local/bin/cursor-agent")
        if (Path.home() / ".local/bin/cursor-agent").exists() else None)
    if not exe:
        return False, "cursor-agent not on PATH"
    try:
        proc = subprocess.run(
            [exe, "--print", "--force", "--output-format", "text",
             brief + _shell_run_facts(base, head, "cursor")],
            cwd=str(workdir), text=True, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=CURSOR_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return False, f"cursor timed out after {CURSOR_TIMEOUT_S}s"
    for candidate in (workdir / "reviewer-report.json", out):
        ok, why = validate_report(candidate, base, head, "cursor")
        if ok:
            if candidate != out:
                # Move, byte-identical: a copy left in the candidate worktree dirties
                # it and the release receipt then refuses ("dirty worktree").
                out.write_bytes(candidate.read_bytes())
                candidate.unlink()
            return True, why
    blob = (proc.stdout or "") + (proc.stderr or "")
    return False, f"no valid report (exit {proc.returncode}): {blob.strip()[-200:]}"


# ── lane 1: codex CLI ───────────────────────────────────────────────────────
def _untracked(workdir: Path) -> set[str]:
    p = subprocess.run(["git", "-C", str(workdir), "ls-files", "--others", "--exclude-standard",
                        "--directory", "-z"], capture_output=True, text=True)
    return {x.rstrip("/") for x in p.stdout.split("\0") if x}


def _evict_new_untracked(workdir: Path, before: set[str], out: Path) -> None:
    """Move what the reviewer left in the worktree (e.g. reviewer-evidence/) next to
    --out: left in place it dirties the tree and the receipt refuses. Moved, never
    deleted, because it is the reviewer's evidence."""
    new = sorted(_untracked(workdir) - before - {"reviewer-report.json"})
    if not new:
        return
    dest = out.parent / f"{out.stem}-evidence"
    dest.mkdir(parents=True, exist_ok=True)
    for rel in new:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(workdir / rel, target)
    print(f"[lane] moved reviewer leftovers {new} -> {dest}", file=sys.stderr)


# Bulk review runs on Sol, not on the account default.
#
# `~/.codex/config.toml` sets model = "gpt-6-astra", which is the expensive top model and the
# right default for interactive founder work. Every automated review inheriting it spends that
# same quota, and the ChatGPT envelope is shared across every Codex surface on the account.
#
# OpenAI's 23/09/2026 announcement measures Sol at xhigh above Claude Opus 5 at max on
# AutomationBench for ~9% of the cost per task, and within 1.1pp of Fable 5 on DeepSWE for ~80%
# less. For reading a diff and naming a mechanism, that is the correct tier — and it leaves Astra
# for the work only Astra can do.
#
# Override with CODEX_REVIEW_MODEL. Set it empty to fall back to the account default, which is
# what you want if the model id is ever retired: an unknown id is refused at the API with
# "model is not supported when using Codex with a ChatGPT account", which fails the lane rather
# than silently downgrading it.
CODEX_REVIEW_MODEL = os.environ.get("CODEX_REVIEW_MODEL", "gpt-6-sol")


def lane_codex(brief: str, workdir: Path, out: Path, base: str, head: str) -> tuple[bool, str]:
    exe = which("codex")
    if not exe:
        return False, "codex not on PATH"
    cmd = [exe, "exec", "--sandbox", "workspace-write"]
    if CODEX_REVIEW_MODEL:
        cmd += ["-m", CODEX_REVIEW_MODEL]
    cmd.append("-")
    before = _untracked(workdir)
    try:
        proc = subprocess.run(
            cmd,
            input=brief + _shell_run_facts(base, head, "codex"), cwd=str(workdir), text=True,
            capture_output=True, timeout=3600,
        )
    except subprocess.TimeoutExpired:
        _evict_new_untracked(workdir, before, out)
        return False, "codex timed out after 3600s"
    _evict_new_untracked(workdir, before, out)
    blob = (proc.stdout or "") + (proc.stderr or "")
    # The report is the verdict, NOT proc.returncode — codex exits 0 on quota exhaustion.
    for candidate in (workdir / "reviewer-report.json", out):
        ok, why = validate_report(candidate, base, head, "codex")
        if ok:
            if candidate != out:
                # Move, byte-identical: a copy left in the candidate worktree dirties
                # it and the release receipt then refuses ("dirty worktree").
                out.write_bytes(candidate.read_bytes())
                candidate.unlink()
            return True, why
    if "usage limit" in blob.lower() or "quota" in blob.lower():
        reset = ""
        m = re.search(r"try again at ([^\n\.]+)", blob)
        if m:
            reset = f" (resets {m.group(1).strip()})"
        return False, f"quota exhausted{reset} — note it EXITED {proc.returncode} with no report"
    return False, f"no valid report (exit {proc.returncode}): {blob.strip()[-200:]}"


def which(name: str) -> str | None:
    from shutil import which as _w
    return _w(name)


# ── HTTP lanes: one prompt, JSON back ───────────────────────────────────────
# HTTP lanes have NO repo, NO shell and NO tools — unlike the codex lane, which
# runs an agent inside `workdir`. Until 19/08/2026 they were handed the brief
# alone and then ordered to "quote a line that exists in the diff", so they were
# asked to review something they had never been shown. Every one of them returned
# FAIL-with-no-findings, and one fabricated a citation (`echo "PASS"`, zero
# occurrences in the 193-line file it named). The diff is not optional context for
# these lanes; it IS the artefact under review, so it is inlined here.
DIFF_BUDGET_CHARS = 400_000


# Captured console output is not reviewable source, and it crowds out what is.
# On 19/08/2026 a 22-commit branch produced a 1.26 MB diff of which 78% was two
# .log artefacts — the reviewer's budget would have been spent on transcript noise
# while the SQL the founder pastes into production fell off the truncated tail.
# Excluded paths are NAMED in the prompt, never dropped silently.
DIFF_EXCLUDE = [":(exclude)*.log", ":(exclude)*.jsonl"]

# Extra pathspecs from --paths, so one pass covers one bounded surface WHOLE
# rather than the whole diff partly. A bounded, declared scope is the correct
# answer to a diff that does not fit the budget; a silent 40% is not.
#
# The exclusion list above was written for exactly this failure on 19/08/2026 and
# aimed at the file EXTENSION that caused it (*.log). By 21/08/2026 the crowd-out
# was ~380k of session-handoff markdown, which it does not match. Same class,
# different extension. Scoping generalises where a deny-list did not.
SCOPE_PATHS: list[str] = []


def _files_after(diff: str, cut: int) -> list[str]:
    """Paths whose diff section begins at or after `cut` — never shown to the model."""
    off, unseen = 0, []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git ") and off >= cut:
            unseen.append(line.strip().split(" b/")[-1])
        off += len(line)
    return unseen


def _excluded_files(workdir: Path, base: str, head: str) -> list[str]:
    try:
        all_f = subprocess.run(["git", "-C", str(workdir), "diff", "--name-only", base, head],
                               text=True, capture_output=True, timeout=60).stdout.split()
        kept = subprocess.run(["git", "-C", str(workdir), "diff", "--name-only", base, head,
                               "--", *DIFF_EXCLUDE],
                              text=True, capture_output=True, timeout=60).stdout.split()
    except (subprocess.TimeoutExpired, OSError):
        return []
    return sorted(set(all_f) - set(kept))


def _diff_block(workdir: Path, base: str, head: str) -> tuple[str, str, dict]:
    """Return (prompt_block, note, coverage).

    `coverage` is the machine-readable half the success path used to discard: how much
    of the diff reached the prompt, which files never did, and any declared scope. The
    note goes to the lane log; the coverage decides whether a PASS is legal.
    """
    pathspec = DIFF_EXCLUDE + list(SCOPE_PATHS)
    try:
        proc = subprocess.run(
            ["git", "-C", str(workdir), "diff", f"{base}", f"{head}", "--", *pathspec],
            text=True, capture_output=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return "", f"diff unavailable ({type(exc).__name__}: {exc})", {}
    if proc.returncode != 0:
        return "", f"diff unavailable (git exit {proc.returncode}: {proc.stderr.strip()[:160]})", {}
    diff = proc.stdout
    skipped = _excluded_files(workdir, base, head)
    if skipped:
        diff = ("[NOT SHOWN — captured log/JSONL artefacts, excluded so the source fits: "
                + ", ".join(skipped) + ". You are not reviewing these; do not claim you did.]\n\n"
                + diff)
    if not diff.strip():
        return "", "diff is empty — nothing to review", {}
    coverage = {"total_chars": len(diff), "shown_chars": len(diff), "truncated": False,
                "excluded_files": skipped, "scope_paths": list(SCOPE_PATHS),
                "unseen_files": []}
    note = f"diff {len(diff)} chars"
    if len(diff) > DIFF_BUDGET_CHARS:
        coverage.update(shown_chars=DIFF_BUDGET_CHARS, truncated=True,
                        unseen_files=_files_after(diff, DIFF_BUDGET_CHARS))
        # Say what was dropped. A silently truncated diff reads as full coverage.
        diff = diff[:DIFF_BUDGET_CHARS]
        note = (f"diff TRUNCATED to {DIFF_BUDGET_CHARS} of {len(proc.stdout)} chars — "
                f"the reviewer did not see the tail")
        diff += (f"\n\n[TRUNCATED at {DIFF_BUDGET_CHARS} characters of "
                 f"{len(proc.stdout)}. You have NOT seen the whole diff. Do not claim "
                 f"coverage of what is not shown; confine findings to what appears above.]\n")
    block = (
        "\n\n════════ THE DIFF UNDER REVIEW (base..head) ════════\n"
        "You have NO shell, NO repo and NO tools. This diff is the only artefact you\n"
        "can see, so every finding must be anchored in a line that appears below. You\n"
        "cannot run the suites or the mutation controls the rubric describes — do not\n"
        "claim you did, and do not treat 'I could not run it' as a defect.\n"
        "Judge the diff on what it shows. FAIL requires at least one finding quoting a\n"
        "real line below — a FAIL naming nothing is discarded and the lane counts as\n"
        "failed. PASS means no P0/P1 is evident IN THIS DIFF; it is not a claim that the\n"
        "branch is safe, and it does not certify anything you could not see.\n"
        "════════════════════════════════════════════════════\n"
        f"{diff}\n"
        "════════ END OF DIFF ════════\n")
    return block, note, coverage


def _report_instruction(base: str, head: str, reviewer: str) -> str:
    return f"""

════════ OUTPUT CONTRACT — THIS OVERRIDES ANY OUTPUT FORMAT ABOVE ════════
Reply with ONE JSON object and NOTHING else. No prose, no markdown fence.

{{
  "schema": 2,
  "implementation_agent": "claude",
  "reviewer_agent": "{reviewer}",
  "reviewer_session_id": "<any stable string identifying this review>",
  "base_sha": "{base}",
  "head_sha": "{head}",
  "verdict": "PASS" or "FAIL",
  "blocking_findings": [
    {{"severity": "P0"|"P1", "title": "<short name for the defect>",
      "file": "<repo-relative path>", "line": <int>,
      "quoted_line": "<a line that EXISTS verbatim in the diff under that file>",
      "reproduction": "<what in the diff shows it>",
      "suggested_fix": "<what closes it>"}}
  ],
  "checklist": [
    {{"id": "<one of the eight ids below>", "verdict": "PASS" or "N/A",
      "evidence": "<what discharged it>", "reason": "<REQUIRED when N/A>"}}
  ],
  "coverage": {{
    "reviewed": ["<exact repo-relative path>"],
    "not_reviewed": [{{"path": "<exact repo-relative path>", "reason": "<why not>"}}]
  }},
  "reviewed_at": "{datetime.now(timezone.utc).isoformat()}"
}}

RULES THAT ARE CHECKED MECHANICALLY, so violating them discards your finding unread:
- Every blocking finding must quote a line that exists in the diff UNDER THE FILE IT NAMES.
- blocking_findings is P0/P1 ONLY. P2s do not block; leave them out.
- verdict PASS means zero P0/P1. If you are uncertain, return FAIL.
- Do not quote a `-` (removed) line and report the branch's own fix as the defect.

ALL EIGHT checklist ids are REQUIRED, spelled exactly:
  coverage-ledger, plan-conformance, weakened-checks, mutation-control,
  guard-falsification, clean-environment-suite, blast-radius, outbound-actions
A checklist verdict is PASS or N/A ONLY, never FAIL. An item you could not discharge is
N/A WITH a reason. A real failure is a blocking finding and takes the verdict with it.

- coverage.reviewed plus coverage.not_reviewed must together name EVERY changed file
  EXACTLY ONCE, spelled exactly as supplied to you, and NOTHING that is not in the diff.
  An omitted file and an invented path are equally fatal to the ledger.
"""


def _http_json(url: str, payload: dict, headers: dict, timeout: int = 900) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


REPORT_MARKERS = ("schema", "base_sha", "head_sha", "checklist", "coverage",
                  "blocking_findings", "reviewer_agent")


def _extract_json(text: str) -> dict | None:
    """Return the RICHEST report-shaped JSON object in a model response.

    The previous version took the FIRST balanced object, and swarm_review.py records
    what that costs (2026-08-17): a reasoning dump quotes schema fragments before and
    after the real report, so `first` caught a prose preamble and `last` caught a
    trailing {"verdict":"PASS"} example — scoring a genuine FAIL-with-P0 as a clean
    PASS. Selecting the wrong object silently FLIPS A VERDICT, so the selector must be
    positive about what a report looks like: report-shaped keys present, more beats
    fewer. A bare {"verdict": ...} fragment scores 0 and can never displace a report.
    """
    if not text:
        return None
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.MULTILINE)
    best, best_score = None, -1
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict):
                        score = sum(1 for m in REPORT_MARKERS if m in obj)
                        if score > best_score:
                            best, best_score = obj, score
                    break
    return best if best_score > 0 else None


def lane_openrouter(brief: str, workdir: Path, out: Path, base: str, head: str) -> tuple[bool, str]:
    key = resolve_secret("OPENROUTER_API_KEY")
    if not key:
        return False, "OPENROUTER_API_KEY not found in env or any known file"
    # FREE MODELS ONLY (founder directive, 18/09/2026, restated 21/09/2026):
    # OpenRouter is the free-model harness. This lane previously defaulted to the
    # paid openai/gpt-5.6-sol (~$1/review) and on 21/09/2026 a release review hit
    # HTTP 402 asking for credits. The default now comes from the measured `free`
    # tier in swarm_tiers.json, and any model without the ":free" suffix is refused
    # before a request is made, env override included. Paid OpenRouter is a founder
    # spend decision, never a fallback.
    try:
        free_tier = json.loads(Path(__file__).with_name("swarm_tiers.json").read_text())
        default_free = free_tier["tiers"]["free"]["models"][0]["id"]
    except Exception as exc:  # noqa: BLE001 - no measured free model = no lane
        return False, f"free tier unreadable in swarm_tiers.json: {exc}"
    model = os.environ.get("PR_GATE_OPENROUTER_MODEL", default_free)
    if not model.endswith(":free"):
        return False, (f"refused paid OpenRouter model {model!r}: OpenRouter is the free-model "
                       "harness only (founder directive); pick a ':free' model")
    diff_block, diff_note, coverage = _diff_block(workdir, base, head)
    if not diff_block:
        return False, diff_note
    prompt = brief + diff_block + _report_instruction(base, head, f"openrouter/{model}")
    try:
        d = _http_json(
            "https://openrouter.ai/api/v1/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": prompt}],
             "temperature": 0.1, "max_tokens": 16000},
            {"Authorization": f"Bearer {key}",
             "HTTP-Referer": "https://github.com/CleanExpo",
             "X-Title": "pr-release-gate independent review"})
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read()[:200].decode(errors='replace')}"
    except Exception as exc:  # noqa: BLE001 - report the blocker, never swallow it
        return False, f"{type(exc).__name__}: {exc}"
    try:
        text = d["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        return False, f"unexpected response shape: {json.dumps(d)[:200]}"
    obj = _extract_json(text or "")
    if obj is None:
        return False, f"no JSON object in the response: {(text or '')[:200]}"
    obj.setdefault("reviewer_agent", f"openrouter/{model}")
    out.write_text(json.dumps(obj, indent=2))
    print(f"[diff] {diff_note}", flush=True)
    return validate_report(out, base, head, obj["reviewer_agent"], coverage)


def lane_gemini(brief: str, workdir: Path, out: Path, base: str, head: str) -> tuple[bool, str]:
    key = resolve_secret("GEMINI_API_KEY")
    if not key:
        return False, "GEMINI_API_KEY not found in env or any known file"
    # gemini-2.5-pro is RETIRED for new users — this key gets HTTP 404 "no longer
    # available to new users". Probed the key's own /models list on 19/08/2026 and
    # pinned what it actually serves. A lane whose default 404s is a lane that only
    # fails at the moment it is needed, which is the whole failure being fixed here.
    model = os.environ.get("PR_GATE_GEMINI_MODEL", "gemini-3.1-pro-preview")
    # 65536 is the model's own outputTokenLimit (probed 16/09/2026), not a guess.
    max_out = int(os.environ.get("PR_GATE_GEMINI_MAX_OUTPUT", "65536"))
    # Leaves ~41k tokens for the report itself. A 169-file coverage ledger plus eight
    # checklist items with evidence is several thousand tokens before any findings.
    think_budget = int(os.environ.get("PR_GATE_GEMINI_THINKING_BUDGET", "24576"))
    diff_block, diff_note, coverage = _diff_block(workdir, base, head)
    if not diff_block:
        return False, diff_note
    prompt = brief + diff_block + _report_instruction(base, head, f"gemini/{model}")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    try:
        d = _http_json(url, {
            "contents": [{"parts": [{"text": prompt}]}],
            # Gemini 3.x are THINKING models and their reasoning is billed against this
            # same budget. At 16000 a real review spent 15360 tokens thinking and had 626
            # left to answer with, so it returned truncated JSON and the lane read as
            # "no JSON object" — a misleading symptom for a budget problem. Keep this
            # high; the answer itself is small.
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": max_out,
                "responseMimeType": "application/json",
                # THINKING IS BILLED AGAINST maxOutputTokens, and this model fills
                # whatever room it is given. Measured 16/09/2026 on a 169-file diff:
                # at maxOutputTokens=65536 it spent 62914 tokens THINKING and had ~2600
                # left to answer with, so it returned truncated JSON and the lane read
                # as "response truncated". The earlier round at 16000 did the same thing
                # (15360 thinking, 626 left). Raising the ceiling cannot fix this —
                # models/gemini-3.1-pro-preview reports outputTokenLimit=65536, so the
                # lane was ALREADY at the model's maximum. Capping the thinking is the
                # only lever that leaves room for the report.
                "thinkingConfig": {"thinkingBudget": think_budget},
            },
        }, {})
    except urllib.error.HTTPError as exc:
        body = exc.read()[:200].decode(errors="replace")
        return False, f"HTTP {exc.code}: {body}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    try:
        cand = d["candidates"][0]
        text = cand["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        return False, f"unexpected response shape: {json.dumps(d)[:200]}"
    obj = _extract_json(text or "")
    if obj is None:
        # Name the real cause. Truncation and refusal both look like "no JSON" otherwise.
        finish = cand.get("finishReason", "?")
        if finish == "MAX_TOKENS":
            thoughts = (d.get("usageMetadata") or {}).get("thoughtsTokenCount")
            return False, (
                f"response truncated (finishReason=MAX_TOKENS, thinking tokens="
                f"{thoughts} of maxOutputTokens={max_out}). Raising maxOutputTokens "
                f"will NOT help — {max_out} is at or near this model's outputTokenLimit. "
                f"LOWER PR_GATE_GEMINI_THINKING_BUDGET (currently {think_budget}) so the "
                f"model keeps room to answer, or narrow the surface with --paths.")
        return False, f"no JSON object (finishReason={finish}): {(text or '')[:200]}"
    obj.setdefault("reviewer_agent", f"gemini/{model}")
    out.write_text(json.dumps(obj, indent=2))
    print(f"[diff] {diff_note}", flush=True)
    return validate_report(out, base, head, obj["reviewer_agent"], coverage)


def lane_ollama(brief: str, workdir: Path, out: Path, base: str, head: str) -> tuple[bool, str]:
    model = os.environ.get("PR_GATE_OLLAMA_MODEL", "gpt-oss:120b-cloud")
    diff_block, diff_note, coverage = _diff_block(workdir, base, head)
    if not diff_block:
        return False, diff_note
    prompt = brief + diff_block + _report_instruction(base, head, f"ollama/{model}")
    try:
        d = _http_json("http://127.0.0.1:11434/api/generate",
                       {"model": model, "prompt": prompt, "stream": False,
                        "options": {"temperature": 0.1, "num_ctx": 32768}}, {})
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"
    obj = _extract_json(d.get("response", ""))
    if obj is None:
        return False, f"no JSON object in the response: {d.get('response','')[:200]}"
    obj.setdefault("reviewer_agent", f"ollama/{model}")
    out.write_text(json.dumps(obj, indent=2))
    print(f"[diff] {diff_note}", flush=True)
    return validate_report(out, base, head, obj["reviewer_agent"], coverage)


# Order matters: strongest independence and strongest measured competence first.
# ollama is LAST and is a genuine fallback — it cannot execute mutants, so a PASS
# from it discharges less than the others. It is better than stopping.
# Founder directives, both of which the restored f12 backup predates:
#   COST LAW 29/08/2026 — free and paid-subscription lanes BEFORE metered ones.
#     OpenRouter's key is metered and uncapped, so it sits THIRD, behind Gemini's
#     free tier. The backup had it second, which is how every Codex outage landed
#     on metered spend by default.
#   OLLAMA REMOVED 29/08/2026 — it could not execute a mutant, its default model
#     was a cloud pointer rather than a local model so the lane was not even free,
#     and the only genuinely local model timed out instead of returning a report.
#     A lane that cannot finish is not a fallback. Three lanes, not four.
# lane_ollama() is left defined but unreferenced rather than deleted: removing it
# is surface this restore does not need to touch.
#   CURSOR FIRST 17/09/2026 — the only lane that produced accepted reviews that
#     month (gemini reports were rejected for lacking mutation evidence; codex was
#     out of quota). It is a paid subscription, not metered, so the cost law holds.
# The transport lives here; WHICH lanes exist, in what order, and what each one is
# allowed to be used for, lives in lane_registry.py. Keeping both in this file is what
# let a hardcoded display outlive the ollama removal (see the comment above), and the
# credential map further down repeated the same mistake one level lower.
_LANE_FUNCS = {
    "cursor": lane_cursor,
    "codex": lane_codex,
    "gemini": lane_gemini,
    "openrouter": lane_openrouter,
}

LANES = []
for _row in lane_registry.ordered():
    _fn = _LANE_FUNCS.get(_row["id"])
    if _fn is None:
        # Fail loudly at import. A registry lane marked live with no driver behind it
        # would otherwise be dropped silently, and the chain would report "every lane
        # failed" while never having tried it.
        raise RuntimeError(
            f"lane {_row['id']!r} is enabled in lane_registry but has no driver in "
            f"_LANE_FUNCS; either implement it or set enabled=False in the registry")
    LANES.append((_row["id"], _fn))


def _probe_credential(row: dict | None) -> str:
    """Interpret a registry credential declaration: the registry says WHAT to look for,
    this says whether it is actually there. Never reads or prints the value."""
    if row is None:
        return "not in the registry"
    cred = row["credential"]
    if cred["kind"] == "binary":
        if which(cred["bin"]):
            return "PATH ok"
        also = cred.get("also")
        if also and Path(also).expanduser().exists():
            return "PATH ok"
        return f"{cred['bin']} not on PATH"
    if cred["kind"] == "secret":
        return "resolved" if resolve_secret(cred["env"]) else "NOT FOUND"
    return f"unknown probe kind {cred['kind']!r}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brief", help="path to the reviewer brief")
    ap.add_argument("--base", help="40-char base SHA")
    ap.add_argument("--head", help="40-char head SHA")
    ap.add_argument("--out", default="reviewer-report.json")
    ap.add_argument("--repo", default=".", help="worktree the reviewer runs in")
    ap.add_argument("--lane", action="append",
                    help="restrict to these lanes, in order (repeatable)")
    ap.add_argument("--paths", action="append", default=[],
                    help="restrict the diff to these pathspecs, so one pass covers one "
                         "bounded surface WHOLE instead of the whole diff partly "
                         "(repeatable). Recorded as diff_coverage.scope_paths")
    ap.add_argument("--list-lanes", action="store_true",
                    help="report which lanes have a resolvable credential, and exit")
    args = ap.parse_args()

    if args.list_lanes:
        # Derived from LANES, never hardcoded. The hardcoded version of this
        # block survived the 29/08/2026 removal of the ollama lane and the
        # cost-law reorder, so it advertised a banned lane and told the reader
        # metered OpenRouter ran second. A lane display that disagrees with the
        # lane reality is how the wrong lane gets chosen.
        # The probe is DESCRIBED in the registry and INTERPRETED here. The registry may
        # not import resolve_secret (that is the import cycle this split exists to
        # break), and this file may not keep its own list of lanes (that is the drift
        # the registry exists to stop). Neither side holds both halves.
        print("order  lane        credential")
        for i, (name, _fn) in enumerate(LANES, 1):
            print(f"{i:>5}  {name:<11} {_probe_credential(lane_registry.lane(name))}")
        # Registered but not routed — shown so a known lane that is merely not live is
        # never mistaken for a lane nobody has heard of.
        for row in lane_registry.ordered(enabled_only=False):
            if not row["enabled"]:
                print(f"    -  {row['id']:<11} {_probe_credential(row)}  "
                      f"[registered, not routed: {row['note'].splitlines()[0]}]")
        return 0

    for required in ("brief", "base", "head"):
        if not getattr(args, required):
            ap.error(f"--{required} is required unless --list-lanes is given")

    brief = Path(args.brief).read_text()
    SCOPE_PATHS.extend(args.paths)
    workdir = Path(args.repo).resolve()
    out = Path(args.out).resolve()

    if args.lane:
        # A typo used to filter `selected` to empty, run nothing, and print the
        # "NO LANE PRODUCED A VALID REPORT" banner with no lanes listed, exiting 2 —
        # byte-identical to genuine total exhaustion. That is how a review that never
        # ran gets recorded as a review that found nothing. Name it instead.
        known = {n for n, _ in LANES}
        unknown = [n for n in args.lane if n not in known]
        if unknown:
            registered = {r["id"] for r in lane_registry.ordered(enabled_only=False)}
            hint = ""
            if set(unknown) & registered:
                hint = (f" (registered but not routed: "
                        f"{', '.join(sorted(set(unknown) & registered))})")
            ap.error(f"unknown lane(s): {', '.join(unknown)}{hint}. "
                     f"Live lanes: {', '.join(sorted(known))}")

    selected = [(n, f) for n, f in LANES if not args.lane or n in args.lane]
    if args.lane:
        order = {n: i for i, n in enumerate(args.lane)}
        selected.sort(key=lambda p: order.get(p[0], 99))

    failures = []
    for name, fn in selected:
        print(f"[lane] {name} …", flush=True)
        try:
            ok, why = fn(brief, workdir, out, args.base, args.head)
        except Exception as exc:  # noqa: BLE001 - a crashing lane must not kill the chain
            ok, why = False, f"lane raised {type(exc).__name__}: {exc}"
        if ok:
            print(f"[lane] {name} PRODUCED A REPORT: {why}")
            print(f"[report] {out}")
            return 0
        print(f"[lane] {name} unavailable: {why}", flush=True)
        failures.append((name, why))

    print("\nNO LANE PRODUCED A VALID REPORT. This is a real blocker, not a vendor outage:")
    for name, why in failures:
        print(f"  {name:12s} {why}")
    print("\nA missing report is the finding. Do NOT record a receipt, and do NOT")
    print("read any lane's exit code as a verdict.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
