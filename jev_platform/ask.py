"""Level 8: ask Jev about files without reading them into an agent's context (PLAN-ask.md rev 4).

Two question types, as in `ask_jev_file_bool` and `ask_jev_file_choice`, with this estate's
boundary on top:
- only files listed in `.jev-approved.json` **at HEAD**, and only when the bytes read hash to
  the approved sha256 (a new, changed or swapped file is refused before any request)
- only question templates listed in the same manifest; there is no free-text question
- each file is opened once, component by component with O_NOFOLLOW, and that exact buffer is sent
- secrets / banned-publisher content in bytes, path or template text -> refused, never sent
- every answer is advisory; any failed or incomplete answer is `unavailable` with no numbers
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat

from jev_platform import client, policy
from jev_platform import committed as verified

MANIFEST = ".jev-approved.json"
MAX_FILE_BYTES = 32_000
MAX_QUESTIONS = 8
MAX_TEMPLATE_CHARS = 1_000
ADVISORY = "advisory, not authorization"
_DENY_NAMES = re.compile(
    r"(^|/)(\.env[^/]*|[^/]*\.(pem|key|p12|pfx|kdbx|tfstate)|[^/]*(id_rsa|id_ed25519|credential|secret)[^/]*"
    r"|\.npmrc|\.netrc|\.pypirc)$|(^|/)(\.git|\.hermes|\.ssh|\.aws|\.vercel|\.gcloud)(/|$)", re.I)
_REFUSE = client.CREDENTIALS + [re.compile(p, re.I | re.ASCII) for p in (client._EDGE + r"iicrc" + client._END,
                                                                 r"standards australia")] \
    + client._PATTERNS


def git_env() -> dict:
    """A fixed minimal environment for git: no inherited variable, so no API key reaches the child."""
    return {"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "HOME": os.path.expanduser("~"),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}


def approved_manifest(repo: str) -> dict | None:
    """The manifest as committed at HEAD; the working copy never counts."""
    found = verified.at_head(repo, MANIFEST, env=git_env())  # round 12: every object on the path rehashed
    if found is None:
        return None
    try:
        data = client.strict_json(found[2])
    except ValueError:
        return None
    if not isinstance(data, dict):  # a list, string, number or null manifest is refused, not a crash
        return None
    return data if isinstance(data.get("files"), dict) and isinstance(data.get("questions"), dict) else None


def sensitive(text: str) -> bool:
    return any(p.search(t) for t in client.screened(text) for p in _REFUSE)


def sensitive_payload(obj) -> bool:
    """Round 20: screen every decoded string key and value of an outbound body, not only its JSON text, where a
    newline or tab before a secret serialises as \\n or \\t and hides the word boundary the patterns need."""
    if isinstance(obj, str):
        return sensitive(obj)
    if isinstance(obj, dict):
        return any(sensitive_payload(k) or sensitive_payload(v) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(sensitive_payload(v) for v in obj)
    return False


def read_confined(repo: str, rel: str) -> bytes:
    """Open repo/rel without following any symlink component; return up to MAX_FILE_BYTES + 1 bytes."""
    parts = rel.split("/")
    if rel.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError("path must be relative, without . or ..")
    fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NONBLOCK)  # NONBLOCK: a FIFO never hangs the open
    try:
        for part in parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            os.close(fd)
            fd = nxt
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)
    try:
        if not stat.S_ISREG(os.fstat(leaf).st_mode):
            raise ValueError("not a regular file")
        return os.read(leaf, MAX_FILE_BYTES + 1)
    finally:
        os.close(leaf)


def _question(tid: str, t: dict) -> dict | None:
    if t.get("type") == "noul" and all(isinstance(t.get(k), str) for k in ("question", "true", "false")):
        return {"type": "noul", "instructions": t["question"], "criteria": {"true": t["true"], "false": t["false"]}}
    if t.get("type") == "choice" and isinstance(t.get("question"), str) and isinstance(t.get("options"), dict) \
            and 2 <= len(t["options"]) <= 255 and all(isinstance(v, str) for v in t["options"].values()):
        return {"type": "choice", "instructions": t["question"], "criteria": dict(t["options"])}
    return None


def build_questions(manifest: dict, template_ids: list[str]) -> tuple[dict | None, str | None]:
    if not template_ids or len(template_ids) > MAX_QUESTIONS:
        return None, f"need 1-{MAX_QUESTIONS} templates"
    if len(set(template_ids)) != len(template_ids):
        return None, "duplicate template"
    questions = {}
    for tid in template_ids:
        t = manifest["questions"].get(tid)
        q = _question(tid, t) if isinstance(t, dict) else None
        if q is None:
            return None, f"unknown or malformed template: {tid}"
        text = json.dumps(q)
        if len(text) > MAX_TEMPLATE_CHARS or sensitive_payload({tid: q}):  # rounds 19-20; all values are strings
            return None, f"template refused: {tid}"
        questions[tid] = q
    return questions, None


def _answer(a, q: dict):
    """One validated answer, or None. Choice picks must be an option or 'other'."""
    if not isinstance(a, dict) or a.get("type") != q["type"]:
        return None
    if q["type"] == "noul":
        return {"type": "noul", "noul": float(a["noul"])} if policy.valid_noul(a.get("noul")) else None
    probs, allowed = a.get("probabilities"), set(q["criteria"]) | {"other"}
    if a.get("choice") not in allowed or not policy.valid_noul(a.get("confidence")) or not isinstance(probs, dict) \
            or not set(probs) <= allowed or not all(policy.valid_noul(v) for v in probs.values()):
        return None
    return {"type": "choice", "choice": a["choice"], "confidence": float(a["confidence"]),
            "probabilities": {k: float(v) for k, v in probs.items()}}


def validate_answers(data, questions: dict) -> dict | None:
    answers = data.get("answers") if isinstance(data, dict) else None
    if not isinstance(answers, dict) or set(answers) != set(questions):
        return None
    out = {tid: _answer(answers[tid], q) for tid, q in questions.items()}
    return None if any(v is None for v in out.values()) else out


def admit(repo: str, manifest: dict, rel: str) -> tuple[str | None, str | None, str | None]:
    """(content, sha256, refusal). Every refusal happens before any request."""
    if _DENY_NAMES.search(rel) or sensitive(rel):
        return None, None, "denied path"
    approved = manifest["files"].get(rel)
    if not isinstance(approved, str):
        return None, None, "not in approved manifest"
    try:
        raw = read_confined(repo, rel)
    except (OSError, ValueError) as e:
        return None, None, f"unreadable: {type(e).__name__}"
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) > MAX_FILE_BYTES:
        return None, digest, "file over 32,000 bytes"
    if digest != approved:
        return None, digest, "content differs from approved sha256"
    text = raw.decode("utf-8", errors="replace")
    if sensitive(text):
        return None, digest, "sensitive content"
    return text, digest, None


def ask_files(repo: str, paths: list[str], template_ids: list[str], post, budget) -> dict:
    manifest = approved_manifest(repo)
    if manifest is None:
        return {"blocked": f"no committed {MANIFEST} at HEAD", "results": []}
    questions, problem = build_questions(manifest, template_ids)
    if problem:
        return {"blocked": problem, "results": []}
    wrong_state = [t for t in template_ids if manifest["questions"][t].get("state", ["content"]) != ["content"]]
    if wrong_state:
        return {"blocked": f"template refused: {', '.join(wrong_state)} reads more than content, "
                           "ask sends content", "results": []}
    results = []
    for rel in paths:
        content, digest, refusal = admit(repo, manifest, rel)
        if refusal:
            results.append({"path": rel, "sha256": digest, "refused": refusal})
            continue
        body = {"state": {"path": rel, "content": content}, "model": "jev-latest", "questions": questions}
        sent = client.send(body, post, budget)
        answers = validate_answers(sent.get("data"), questions) if "data" in sent else None
        if answers is None:
            results.append({"path": rel, "sha256": digest,
                            "unavailable": sent.get("error", "signal_unavailable:invalid_response")})
            continue
        results.append({"path": rel, "sha256": digest, "model": str(sent["data"].get("model", "unknown")),
                        "answers": answers, "note": ADVISORY})
    return {"results": results, "spent_usd": round(budget.spent, 6), "attempts": budget.attempts}


def approve_entry(repo: str, rel: str) -> dict:
    """What a human would paste into the manifest for this file. Never writes the manifest."""
    raw = read_confined(repo, rel)
    return {rel: hashlib.sha256(raw).hexdigest()}
