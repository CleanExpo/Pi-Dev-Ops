"""The Gemini Flash agent runner: `python -m jev_platform agent --prompt ID` (PLAN-scale.md rev 5).

A function-calling loop over generateContent (model pinned to gemini-3.8-flash, thinking low).
The operator prompt is an approved prompt id, never free text. Tools: ask_jev_files,
pick_first_file, ask_jev, read_file, propose_template; nothing writes, edits, runs commands or
approves. Caps: US$0.10 per run, 12 turns, 24 count calls. Any outage, safety block, empty
candidate, malformed call, overrun or cap ends the run `incomplete: <reason>`. The report is
rendered by code from the ledger; the model's closing prose is shown as unverified.
"""
from __future__ import annotations

import json
import sys
import time

from jev_platform import agent_tools, cli_scale, client, gemini
from jev_platform import manifest as mf

SYSTEM = (
    "You coordinate questions to Jev, a judgment model, about files in an approved manifest. You choose "
    "identifiers only: approved paths, glob patterns over those paths, and template ids. Prefer ask_jev_files and "
    "pick_first_file over read_file; open a file only when the task needs its bytes. You cannot write, edit, run "
    "commands or approve anything. When you are done, reply with a short plain summary and no tool call.")
_SAFETY = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY"}


def system_text(manifest: dict) -> str:
    lines = [SYSTEM, "", "Approved paths:", *sorted(manifest["files"]), "", "Templates (id [state] type: text):"]
    for tid, t in sorted(manifest["questions"].items()):
        lines.append(f"{tid} [{', '.join(mf.template_state(t))}] {t['type']}: {t['question']}")
    return "\n".join(lines)


def parse_reply(data) -> tuple[dict | None, list, str, str | None]:
    """(model content to echo, function calls, text, problem)."""
    cands = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(cands, list) or not cands or not isinstance(cands[0], dict):
        blocked = isinstance(data, dict) and isinstance(data.get("promptFeedback"), dict) \
            and data["promptFeedback"].get("blockReason")
        return None, [], "", "safety block" if blocked else "empty candidate"
    finish = cands[0].get("finishReason")
    if finish in _SAFETY:
        return None, [], "", "safety block"
    if finish == "MAX_TOKENS":
        return None, [], "", "output cap reached"
    content = cands[0].get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list) or not parts or not all(isinstance(p, dict) for p in parts):
        return None, [], "", "empty candidate"
    calls = [p["functionCall"] for p in parts if "functionCall" in p]
    if finish == "MALFORMED_FUNCTION_CALL" or not all(
            isinstance(c, dict) and c.get("name") in agent_tools.PARAMS for c in calls):
        return None, [], "", "malformed function call"
    text = "".join(p["text"] for p in parts if isinstance(p.get("text"), str) and not p.get("thought"))
    return content, calls, text, None


def new_ledger(prompt_id: str) -> dict:
    return {"agent_model": gemini.MODEL, "prompt_id": prompt_id, "turns": 0, "jev_calls": 0, "questions": 0,
            "files_read": 0, "outcome": "incomplete: not started", "summary": ""}


def finish(ledger: dict, run, gem: gemini.GeminiBudget, jev: client.Budget, outcome: str) -> dict:
    """Every count comes from what code saw sent, never from the model's claims."""
    if run is not None:
        ledger.update({"jev_calls": len(run.sends),
                       "questions": sum(len(b.get("questions", {})) for b in run.sends),
                       "files_read": run.files_read, "tool_calls": run.tool_calls, "jev_results": run.results,
                       "reads": run.reads, "proposals": run.proposals})
    ledger.update({"gemini": gem.snapshot(), "jev_usd": round(jev.spent, 6), "gemini_usd": round(gem.spent, 6),
                   "price_table": {gemini.MODEL: gem.price}, "outcome": outcome})
    return ledger


def _turn(run, contents: list, system: str, key: str, gem, http_post, sleep) -> tuple[str | None, str]:
    """One model turn. (outcome when the run ends here, else None; the model's text)."""
    body = gemini.request_body(contents, system, agent_tools.DECLARATIONS)
    sent = gemini.call(body, key, gem, http_post, sleep)
    if "error" in sent:
        return f"incomplete: {sent['error']}", ""
    content, calls, text, problem = parse_reply(sent["data"])
    if problem:
        return f"incomplete: {problem}", ""
    contents.append(content)
    if not calls:
        return "complete", text
    parts = [{"functionResponse": {"name": c["name"], "response": agent_tools.dispatch(run, c["name"], c.get("args", {}))}}
             for c in calls]
    contents.append({"role": "user", "parts": parts})
    return None, text


def run_agent(repo: str, prompt_id: str, key: str, http_post, jev_post, gem: gemini.GeminiBudget,
              jev: client.Budget, sleep=time.sleep) -> dict:
    ledger = new_ledger(prompt_id)
    manifest, problem = mf.load_manifest(repo)
    prompt = mf.prompt_text(manifest, prompt_id) if manifest else None
    if problem or prompt is None:
        return finish(ledger, None, gem, jev, f"incomplete: {problem or 'unknown prompt id'}")
    run = agent_tools.Run(repo, manifest, prompt_id, jev_post, jev)
    contents, system, outcome = [{"role": "user", "parts": [{"text": prompt}]}], system_text(manifest), None
    gem.start_batch()
    for turn in range(gemini.TURN_CAP):
        ledger["turns"] = turn + 1
        outcome, text = _turn(run, contents, system, key, gem, http_post, sleep)
        if outcome is not None:
            ledger["summary"] = text
            break
    return finish(ledger, run, gem, jev, outcome or "incomplete: turn cap")


def _answer_lines(entry: dict) -> list[str]:
    out, tool = entry["result"], entry["tool"]
    if tool == "ask_jev_files":
        rows = agent_tools.project_scout(out)
        return [f"  {json.dumps(r, sort_keys=True)}" for r in rows.get("files", [rows])]
    view = agent_tools.project_pick(out) if tool == "pick_first_file" else agent_tools.project_bundle(out)
    return [f"  {tool}: {json.dumps(view, sort_keys=True)}"]


def render_report(ledger: dict) -> str:
    """Rendered by code from the ledger. The agent's prose never fills a gap in it."""
    lines = [f"Jev agent run, prompt {ledger['prompt_id']}: {ledger['outcome']}",
             f"agent model {ledger['agent_model']}, turns {ledger['turns']}, Jev calls {ledger['jev_calls']}, "
             f"questions {ledger['questions']}, files read {ledger['files_read']}",
             f"Jev US${ledger['jev_usd']}, Gemini US${ledger['gemini_usd']}, price table {json.dumps(ledger['price_table'])}",
             f"Gemini ledger {json.dumps(ledger['gemini'], sort_keys=True)}", "", "Jev answers:"]
    for entry in ledger.get("jev_results", []):
        lines += _answer_lines(entry)
    lines += ["", "Files read:"] + [f"  {json.dumps(r, sort_keys=True)}" for r in ledger.get("reads", [])]
    lines += ["", "proposed templates (not sent, needs review):"]
    lines += [f"  {json.dumps(p, sort_keys=True)}" for p in ledger.get("proposals", [])]
    lines += ["", "agent summary (unverified):", f"  {ledger.get('summary') or '(none)'}"]
    return "\n".join(lines)


def cmd_agent(a) -> int:
    """The key check runs first, before any prompt-id or manifest work."""
    key = gemini.api_key()
    if not key:
        print(f"BLOCKED: GEMINI_API_KEY not in environment ({gemini.KEY_ROUTE})", file=sys.stderr)
        return 2
    price = gemini.price_table(gemini.today())
    if price is None:
        print("BLOCKED: price table expired", file=sys.stderr)
        return 2
    repo = cli_scale.repo_root(a.repo) if cli_scale._jev_ready() else None
    manifest, problem = mf.load_manifest(repo) if repo else (None, "no repository or no Jev key")
    if problem or mf.prompt_text(manifest, a.prompt_id) is None:
        print(f"REFUSED: {problem or '--prompt must name an approved prompt id'}", file=sys.stderr)
        return 2
    ledger = run_agent(repo, a.prompt_id, key, a.gemini_post, a.post, gemini.GeminiBudget(min(a.max_usd, gemini.RUN_CAP_USD), price),
                       client.Budget(a.jev_max_usd, a.max_seconds))
    print(render_report(ledger))
    if a.ledger:
        with open(a.ledger, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=1)
    return 0 if ledger["outcome"] == "complete" else 1


def register(sub, post) -> None:
    g = sub.add_parser("agent", help="Gemini Flash runner over Levels 9/10 for one approved prompt id")
    g.add_argument("--prompt", "--prompt-id", dest="prompt_id", help="approved prompt id (never free text)")
    g.add_argument("--repo", help="absolute repository path (default: the current directory's repo)")
    g.add_argument("--max-usd", type=float, default=gemini.RUN_CAP_USD)
    g.add_argument("--jev-max-usd", type=float, default=0.75)
    g.add_argument("--max-seconds", type=float, default=900)
    g.add_argument("--ledger", help="also write the ledger JSON to this path")
    g.set_defaults(func=cmd_agent, post=post, gemini_post=gemini.urllib_post)
