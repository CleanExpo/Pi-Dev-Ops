"""Levels 9 and 10: ask_jev_files, pick_first_file and ask_jev (PLAN-scale.md rev 5).

Every Jev body is assembled by code from reviewed parts only: template text, approved file bytes,
the approved prompt's exact text (`task`) and `f`-keys over approved paths. No model-written text
reaches Jev. Every serialised body is screened again with `sensitive()` before it is sent.
Answers stay advisory; any failed or incomplete answer is `unavailable` with no numbers.
"""
from __future__ import annotations

import json

from jev_platform import ask, client, policy
from jev_platform import manifest as mf

MAX_SCOUT_FILES = 255
MAX_PICK = 250
MAX_BUNDLE = 20
CAP_REASON = "over the 255 file cap; narrow the pattern"
MODEL = "jev-latest"


def guarded_send(body: dict, post, budget: client.Budget) -> dict:
    """client.send, after a last screen of the whole serialised body."""
    body = json.loads(json.dumps(body))  # round 25: the screened bytes are the bytes sent, on every retry
    if ask.sensitive(json.dumps(body), decode=False) or ask.sensitive_payload(body):  # round 20: decoded strings too
        return {"error": "refused: sensitive payload"}
    return client.send(body, post, budget)


def _setup(repo: str, tool: str, template_ids: list[str], prompt_id) -> tuple[dict | None, str | None, str | None]:
    manifest, problem = mf.load_manifest(repo)
    if problem:
        return None, None, problem
    task = None
    if prompt_id is not None or tool in ("pick_first_file", "ask_jev"):
        task = mf.prompt_text(manifest, prompt_id)
        if task is None:
            return None, None, "unknown prompt id; only approved prompt ids are accepted"
    problem = mf.incompatible(manifest, tool, template_ids)
    return (None, None, problem) if problem else (manifest, task, None)


def _state(task: str | None, content: str) -> dict:
    return {"content": content} if task is None else {"task": task, "content": content}


def _admit_all(repo: str, manifest: dict, paths: list[str]) -> tuple[list, list]:
    admitted, skipped = [], []
    for rel in paths:
        content, digest, refusal = ask.admit(repo, manifest, rel)
        if refusal:
            skipped.append({"path": rel, "reason": refusal})
        else:
            admitted.append((rel, content, digest))
    return admitted, skipped


def _file_result(rel: str, digest: str, sent: dict, questions: dict) -> dict:
    answers = ask.validate_answers(sent.get("data"), questions) if "data" in sent else None
    if answers is None:
        return {"path": rel, "sha256": digest, "unavailable": sent.get("error", "signal_unavailable:invalid_response")}
    return {"path": rel, "sha256": digest, "model": str(sent["data"].get("model", "unknown")),
            "answers": answers, "note": ask.ADVISORY}


def scout_files(repo: str, patterns: list[str], template_ids: list[str], post, budget: client.Budget,
                prompt_id=None) -> dict:
    """Level 9 ask_jev_files: one sequential Jev call per approved file matching the patterns."""
    tool = "ask_jev_files" if prompt_id is None else "ask_jev_files+task"
    manifest, task, problem = _setup(repo, tool, template_ids, prompt_id)
    questions, problem = (None, problem) if problem else ask.build_questions(manifest, template_ids)
    if problem:
        return {"blocked": problem, "results": [], "skipped": []}
    matched = mf.expand(manifest["files"], patterns)
    admitted, skipped = _admit_all(repo, manifest, matched)
    if len(admitted) > MAX_SCOUT_FILES:
        skipped += [{"path": rel, "reason": CAP_REASON} for rel, _, _ in admitted[MAX_SCOUT_FILES:]]
        admitted = admitted[:MAX_SCOUT_FILES]
    results = []
    for i, (rel, content, digest) in enumerate(admitted):
        body = {"state": _state(task, content), "model": MODEL, "questions": questions}
        sent = guarded_send(body, post, budget)
        if sent.get("error") == "budget_exhausted":
            skipped += [{"path": r, "reason": "budget exhausted"} for r, _, _ in admitted[i:]]
            break
        results.append(_file_result(rel, digest, sent, questions))
    return {"results": results, "skipped": skipped, "spent_usd": round(budget.spent, 6), "attempts": budget.attempts}


def _pick_answer(data, tid: str, keys: dict) -> tuple | None:
    answers = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(answers, dict) or set(answers) != {tid} or not isinstance(answers[tid], dict):
        return None
    a, allowed = answers[tid], set(keys) | {"none", "other"}
    probs = a.get("probabilities")
    if a.get("type") != "choice" or not policy.valid_noul(a.get("confidence")) or not isinstance(probs, dict) \
            or not all(policy.valid_noul(v) for v in probs.values()):
        return None
    if a.get("choice") not in allowed or not set(probs) <= allowed:
        return None
    return a["choice"], float(a["confidence"]), {k: float(v) for k, v in probs.items()}


def _pick_result(sent: dict, tid: str, keys: dict, floor: float) -> dict:
    if "data" not in sent:
        return {"outcome": "unavailable", "reason": sent.get("error", "signal_unavailable")}
    parsed = _pick_answer(sent["data"], tid, keys)
    if parsed is None:
        return {"outcome": "unavailable", "reason": "signal_unavailable:invalid_response"}
    choice, confidence, probs = parsed
    numbers = {"confidence": confidence, "probabilities": {keys.get(k, k): v for k, v in probs.items()}}
    if choice in ("none", "other") or confidence < floor:
        return {"outcome": "none", "choice": choice, "floor": floor, **numbers}
    return {"outcome": "picked", "path": keys[choice], **numbers}


def _pick_candidates(manifest: dict, candidates: list[str]) -> tuple[list, list]:
    paths, refused = [], []
    for rel in dict.fromkeys(candidates):
        if rel in manifest["files"] and not (ask._DENY_NAMES.search(rel) or ask.sensitive(rel)):
            paths.append(rel)
        else:
            refused.append({"path": rel, "reason": "not an approved path"})
    refused += [{"path": rel, "reason": "over the 250 candidate cap"} for rel in paths[MAX_PICK:]]
    return paths[:MAX_PICK], refused


def pick_first(repo: str, prompt_id, template_id: str, candidates: list[str], post, budget: client.Budget,
               floor: float = 0.3) -> dict:
    """Level 9 pick_first_file: one Jev choice over f001..fN (+ none) keyed approved paths."""
    manifest, task, problem = _setup(repo, "pick_first_file", [template_id], prompt_id)
    if not problem and manifest["questions"][template_id].get("type") != "pick":
        problem = f"template {template_id} is not a pick template"
    if problem:
        return {"outcome": "refused", "reason": problem}
    paths, refused = _pick_candidates(manifest, candidates)
    if not paths:
        return {"outcome": "none", "reason": "no candidates", "requests": 0, "refused": refused}
    keys = {f"f{i:03d}": rel for i, rel in enumerate(paths, 1)}
    t = manifest["questions"][template_id]
    question = {"type": "choice", "instructions": t["question"], "criteria": {**keys, "none": t["none"]}}
    body = {"state": {"task": task, "files": keys}, "model": MODEL, "questions": {template_id: question}}
    return {**_pick_result(guarded_send(body, post, budget), template_id, keys, floor), "refused": refused}


def _bundle(repo: str, manifest: dict, paths: list[str]) -> tuple[dict, dict, str | None]:
    if not paths or len(paths) > MAX_BUNDLE or len(set(paths)) != len(paths):
        return {}, {}, f"need 1-{MAX_BUNDLE} distinct paths"
    files, digests = {}, {}
    for rel in paths:
        content, digest, refusal = ask.admit(repo, manifest, rel)
        if refusal:
            return {}, {}, f"{rel}: {refusal}"
        files[rel], digests[rel] = content, digest
    return files, digests, None


def _sizes(body: dict) -> dict:
    return {"task": len(json.dumps(body["state"]["task"]).encode()),
            "files": {p: len(json.dumps(c).encode()) for p, c in body["state"]["files"].items()},
            "questions": len(json.dumps(body["questions"]).encode()), "total": len(json.dumps(body).encode())}


def ask_jev(repo: str, prompt_id, paths: list[str], template_ids: list[str], post, budget: client.Budget) -> dict:
    """Level 10: ONE Jev call over up to 20 approved files and up to 8 [task, files] templates."""
    manifest, task, problem = _setup(repo, "ask_jev", template_ids, prompt_id)
    questions, problem = (None, problem) if problem else ask.build_questions(manifest, template_ids)
    files, digests, problem = ({}, {}, problem) if problem else _bundle(repo, manifest, paths)
    if problem:
        return {"outcome": "refused", "reason": problem}
    body = {"state": {"task": task, "files": files}, "model": MODEL, "questions": questions}
    if len(json.dumps(body).encode()) > client.MAX_REQUEST_BYTES:
        return {"outcome": "refused", "reason": "aggregate over 64,000 bytes", "sizes": _sizes(body)}
    sent = guarded_send(body, post, budget)
    answers = ask.validate_answers(sent.get("data"), questions) if "data" in sent else None
    if answers is None:
        return {"outcome": "unavailable", "reason": sent.get("error", "signal_unavailable:invalid_response"),
                "sha256": digests}
    return {"outcome": "answered", "answers": answers, "sha256": digests, "note": ask.ADVISORY,
            "model": str(sent["data"].get("model", "unknown"))}
