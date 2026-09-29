"""Shared offline fixtures for the Level 9/10, Gemini and agent tests (PLAN-scale.md rev 5). No network."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from jev_platform import ask, client, gemini

GOOD = "export function prorate(a, d) { return Math.round(a * d) / 100; } // TODO rounding\n"
PROMPTS = {"p3": "The proration test fails because of rounding. Find the file to open first.",
           "p1": "Tell me which files admit a known bug, a TODO or a shortcut."}
TEMPLATES = {
    "known-issue": {"type": "noul", "question": "Does `content` contain a known bug, a TODO, or a shortcut?",
                    "true": "It admits a bug, TODO or shortcut", "false": "It admits none of those"},
    "layer": {"type": "choice", "question": "Which layer does `content` belong to?",
              "options": {"http_handler": "HTTP routing and endpoints", "domain_logic": "Business rules",
                          "data_access": "Persistence and queries"}},
    "relevant-to-task": {"type": "noul", "state": ["task", "content"],
                         "question": "Is `content` relevant to fixing the problem described in `task`?",
                         "true": "Changing this file could fix the problem", "false": "It is unrelated"},
    "pick-first-for-task": {"type": "pick", "state": ["task", "files"],
                            "question": "Which one of `files` should be opened first to work on `task`?",
                            "none": "No listed file fits the task"},
    "triage-bundle": {"type": "noul", "state": ["task", "files"],
                      "question": "Do the `files` together contain the cause of the problem in `task`?",
                      "true": "The cause is in these files", "false": "The cause is elsewhere"},
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def git(repo, *args) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


def make_repo(root: Path, files: dict, approved: dict | None = None, questions: dict | None = None,
              prompts: dict | None = None) -> str:
    """Write files, approve `approved` (default: all of them) at HEAD, and commit everything."""
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    approved = files if approved is None else approved
    manifest = {"files": {r: sha(t) for r, t in approved.items()}, "questions": questions or TEMPLATES,
                "prompts": PROMPTS if prompts is None else prompts}
    (root / ask.MANIFEST).write_text(json.dumps(manifest))
    git(root, "init", "-q")
    git(root, "add", "-f", ".")
    git(root, "commit", "-qm", "fixture")
    return str(root)


def answer_all(body: dict) -> dict:
    """A well-formed Jev reply for every question in the body: noul 0.9, or the first option at 0.9."""
    out = {}
    for tid, q in body["questions"].items():
        if q["type"] == "noul":
            out[tid] = {"type": "noul", "noul": 0.9}
        else:
            k = next(iter(q["criteria"]))
            out[tid] = {"type": "choice", "choice": k, "confidence": 0.9, "probabilities": {k: 0.9, "other": 0.1}}
    return {"model": "jev-1.13.0", "answers": out, "usage": {"input_tokens": 500}}


class Recorder:
    """A fake Jev `post`: records every body it is handed and replies with `response(body)`."""

    def __init__(self, response=answer_all, status: int = 200):
        self.calls, self.status, self.response = [], status, response

    def __call__(self, body: dict, timeout: float):
        self.calls.append(body)
        return self.status, self.response(body) if callable(self.response) else self.response, None


def budget(usd: float = 0.75) -> client.Budget:
    return client.Budget(usd, 600)


USAGE = {"promptTokenCount": 100, "candidatesTokenCount": 20, "thoughtsTokenCount": 10}


def fcall(*calls, usage=USAGE) -> dict:
    """A Gemini reply holding function calls, each given as (name, args)."""
    parts = [{"functionCall": {"name": n, "args": a}} for n, a in calls]
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}],
            "usageMetadata": usage}


def ftext(text: str, usage=USAGE) -> dict:
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": usage}


class FakeGemini:
    """A fake Gemini `http_post`. `replies` feed generateContent in order as (status, data) or data;
    `counts` feed countTokens the same way and repeat the last one."""

    def __init__(self, replies=(), counts=((200, {"totalTokens": 100}),)):
        self.calls, self.replies, self.counts = [], list(replies), list(counts)

    def __call__(self, url, payload, headers, timeout):
        self.calls.append((url, payload, headers))
        queue = self.counts if url == gemini.COUNT_URL else self.replies
        item = queue.pop(0) if len(queue) > 1 or url != gemini.COUNT_URL else queue[0]
        return item if isinstance(item, tuple) else (200, item)

    def urls(self) -> list[str]:
        return ["count" if u.endswith(":countTokens") else "generate" for u, _, _ in self.calls]

    def generate_bodies(self) -> list[dict]:
        return [json.loads(p) for u, p, _ in self.calls if u.endswith(":generateContent")]
