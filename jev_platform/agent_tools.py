"""Tools for the Gemini agent runner and the model-visible projection (PLAN-scale.md rev 5).

The agent chooses identifiers only (template ids, approved paths, glob patterns); code builds every
Jev body. Tool results shown to the model are a minimal projection: path, template id, then the typed
answer, `unavailable: <reason>`, `refused: <reason>` or `skipped: <reason>`. No sha256, no bytes (except
`read_file`, which passes admit()), no error bodies. Hashes and raw results stay in the local ledger.
"""
from __future__ import annotations

from jev_platform import ask, client, scout

JEV_TOOLS = ("ask_jev_files", "pick_first_file", "ask_jev")
PROPOSED = "recorded, not sent"
_LIST = {"type": "array", "items": {"type": "string"}}
_STR = {"type": "string"}
PARAMS = {
    "ask_jev_files": {"patterns": _LIST, "template_ids": _LIST},
    "pick_first_file": {"template_id": _STR, "paths": _LIST},
    "ask_jev": {"paths": _LIST, "template_ids": _LIST},
    "read_file": {"path": _STR},
    "propose_template": {"template_id": _STR, "type": _STR, "question": _STR, "criteria": _LIST},
}
_DESCRIPTIONS = {
    "ask_jev_files": "Ask approved question templates about every approved file matching the glob patterns. "
                     "One Jev call per file; you never see the file bytes.",
    "pick_first_file": "Ask Jev which ONE of the approved paths to open first for the task, using a pick template.",
    "ask_jev": "Ask approved [task, files] templates in ONE Jev call over up to 20 approved paths bundled together.",
    "read_file": "Read one approved file. This is the only way file bytes reach you; use it sparingly.",
    "propose_template": "Draft a new question template. It is recorded for human review and never sent to Jev.",
}
DECLARATIONS = [{"functionDeclarations": [
    {"name": n, "description": _DESCRIPTIONS[n],
     "parameters": {"type": "object", "properties": p, "required": [k for k in p if n != "propose_template"]}}
    for n, p in PARAMS.items()]}]


class Run:
    """Per-run state. `sends` is the client's own send log: every body handed to the Jev transport."""

    def __init__(self, repo: str, manifest: dict, prompt_id: str, post, budget: client.Budget):
        self.repo, self.manifest, self.prompt_id, self.budget, self._post = repo, manifest, prompt_id, budget, post
        self.sends, self.results, self.reads, self.proposals, self.tool_calls = [], [], [], [], {}
        self.files_read = 0

    def jev_post(self, body: dict, timeout: float):
        self.sends.append(body)
        return self._post(body, timeout)


def args_problem(name: str, args) -> str | None:
    """Arguments are checked against the declared schema; anything else (e.g. `command`) is refused."""
    if not isinstance(args, dict):
        return "arguments must be an object"
    extra = sorted(set(args) - set(PARAMS[name]))
    if extra:
        return f"unexpected argument: {', '.join(extra)}"
    for k, schema in PARAMS[name].items():
        v = args.get(k)
        if v is None and name == "propose_template":
            continue
        ok = isinstance(v, str) if schema is _STR else isinstance(v, list) and all(isinstance(x, str) for x in v)
        if not ok:
            return f"argument {k} must be {'a string' if schema is _STR else 'a list of strings'}"
    return None


def _typed(a: dict) -> dict:
    if a["type"] == "noul":
        return {"noul": round(a["noul"], 4)}
    return {"choice": a["choice"], "confidence": round(a["confidence"], 4),
            "probabilities": {k: round(v, 4) for k, v in a["probabilities"].items()}}


def project_scout(out: dict) -> dict:
    if "blocked" in out:
        return {"refused": out["blocked"]}
    rows = []
    for r in out["results"]:
        base = {"path": r["path"]}
        if "answers" in r:
            rows += [{**base, "template_id": t, "answer": _typed(a)} for t, a in r["answers"].items()]
        else:
            rows.append({**base, "unavailable": r["unavailable"]})
    rows += [{"path": s["path"], "skipped": s["reason"]} for s in out["skipped"]]
    return {"files": rows}


def _numbers(out: dict) -> dict:
    return {"confidence": round(out["confidence"], 4),
            "probabilities": {k: round(v, 4) for k, v in out["probabilities"].items()}}


def project_pick(out: dict) -> dict:
    refused = [{"path": r["path"], "refused": r["reason"]} for r in out.get("refused", [])]
    if out["outcome"] == "picked":
        return {"picked": out["path"], **_numbers(out), "candidates_refused": refused}
    if out["outcome"] == "none" and "confidence" in out:
        return {"none": f"jev chose {out['choice']} (floor {out['floor']})", **_numbers(out),
                "candidates_refused": refused}
    key = "none" if out["outcome"] == "none" else out["outcome"]
    return {key: out.get("reason", "no reason given"), "candidates_refused": refused}


def project_bundle(out: dict) -> dict:
    if out["outcome"] == "answered":
        return {"answers": {t: _typed(a) for t, a in out["answers"].items()}}
    extra = {"sizes": out["sizes"]} if "sizes" in out else {}
    return {out["outcome"]: out["reason"], **extra}


def _ask_jev_files(run: Run, args: dict) -> dict:
    out = scout.scout_files(run.repo, args["patterns"], args["template_ids"], run.jev_post, run.budget,
                            prompt_id=run.prompt_id)
    run.results.append({"tool": "ask_jev_files", "args": args, "result": out})
    return project_scout(out)


def _pick_first_file(run: Run, args: dict) -> dict:
    out = scout.pick_first(run.repo, run.prompt_id, args["template_id"], args["paths"], run.jev_post, run.budget)
    run.results.append({"tool": "pick_first_file", "args": args, "result": out})
    return project_pick(out)


def _ask_jev(run: Run, args: dict) -> dict:
    out = scout.ask_jev(run.repo, run.prompt_id, args["paths"], args["template_ids"], run.jev_post, run.budget)
    run.results.append({"tool": "ask_jev", "args": args, "result": out})
    return project_bundle(out)


def _read_file(run: Run, args: dict) -> dict:
    content, digest, refusal = ask.admit(run.repo, run.manifest, args["path"])
    run.reads.append({"path": args["path"], "sha256": digest, **({"refused": refusal} if refusal else {})})
    if refusal:
        return {"path": args["path"], "refused": refusal}
    run.files_read += 1
    return {"path": args["path"], "content": content}


def _propose_template(run: Run, args: dict) -> dict:
    run.proposals.append(args)
    return {"result": PROPOSED}


HANDLERS = {"ask_jev_files": _ask_jev_files, "pick_first_file": _pick_first_file, "ask_jev": _ask_jev,
            "read_file": _read_file, "propose_template": _propose_template}


def dispatch(run: Run, name: str, args) -> dict:
    """Run one tool call and return what the model may see. Unknown names are caught by the caller."""
    run.tool_calls[name] = run.tool_calls.get(name, 0) + 1
    problem = args_problem(name, args)
    return {"refused": problem} if problem else HANDLERS[name](run, args)
