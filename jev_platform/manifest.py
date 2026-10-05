"""Manifest rules for Levels 9 and 10 (PLAN-scale.md rev 5): prompts, template state, globs, compatibility.

The manifest at HEAD is the only disclosure boundary. It gains:
- `prompts`: prompt id -> exact operator prompt text. A run takes an id, never free text.
- an optional `state` on each template, naming the code-assembled state fields it reads.
- a `pick` template type for `pick_first_file`, whose options are built by code (f001..fN + none).
Globs are matched against the manifest's `files` keys, never the disk. Nothing here writes the manifest.
"""
from __future__ import annotations

import hashlib
import re
import subprocess

from jev_platform import ask

STATES = {("content",), ("task", "content"), ("task", "files")}
DEFAULT_STATE = ("content",)
MAX_OPTIONS = 250
TOOL_STATE = {"ask_jev_files": ("content",), "ask_jev_files+task": ("task", "content"),
              "pick_first_file": ("task", "files"), "ask_jev": ("task", "files")}
ACCEPTS = {"ask_jev_files": {("content",)}, "ask_jev_files+task": {("content",), ("task", "content")},
           "pick_first_file": {("task", "files")}, "ask_jev": {("task", "files")}}


def template_state(t: dict) -> tuple:
    return tuple(t.get("state", DEFAULT_STATE))


def _shape_problem(tid: str, t: dict) -> str | None:
    kind = t.get("type")
    if kind == "noul":
        ok = all(isinstance(t.get(k), str) and t[k].strip() for k in ("true", "false"))
        return None if ok else f"template {tid}: noul needs non-empty true and false criteria"
    if kind == "choice":
        opts = t.get("options")
        ok = isinstance(opts, dict) and 2 <= len(opts) <= MAX_OPTIONS and all(
            isinstance(v, str) and v.strip() for v in opts.values())
        return None if ok else f"template {tid}: choice needs 2-{MAX_OPTIONS} described options"
    if kind == "pick":
        if template_state(t) != ("task", "files"):
            return f"template {tid}: a pick template must declare state [task, files]"
        return None if isinstance(t.get("none"), str) and t["none"].strip() else f"template {tid}: pick needs none"
    return f"template {tid}: unknown type"


def template_problem(tid: str, t) -> str | None:
    """Why this template may not be loaded, or None. Checked for every template at load."""
    if not isinstance(t, dict) or not isinstance(t.get("question"), str) or not t["question"].strip():
        return f"template {tid}: needs question text"
    state = t.get("state", list(DEFAULT_STATE))
    if not isinstance(state, list) or tuple(state) not in STATES:
        return f"template {tid}: unknown state {state!r}"
    missing = [f for f in state if not re.search(rf"\b{f}\b", t["question"])]
    if missing:
        return f"template {tid} declares {', '.join(missing)} but its text never names it"
    if len(t["question"]) > ask.MAX_TEMPLATE_CHARS:
        return f"template {tid}: question over {ask.MAX_TEMPLATE_CHARS} characters"
    return _shape_problem(tid, t)


def load_manifest(repo: str) -> tuple[dict | None, str | None]:
    """(manifest, problem). Prompts and every template are validated before anything can be sent."""
    manifest = ask.approved_manifest(repo)
    if manifest is None:
        return None, f"no committed {ask.MANIFEST} at HEAD"
    prompts = manifest.setdefault("prompts", {})
    if not isinstance(prompts, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in prompts.items()):
        return None, "prompts must map ids to non-empty text"
    for tid, t in manifest["questions"].items():
        problem = template_problem(tid, t)
        if problem:
            return None, problem
    return manifest, None


def prompt_text(manifest: dict, prompt_id) -> str | None:
    """The approved prompt's exact text. Anything that is not an approved id is refused."""
    text = manifest["prompts"].get(prompt_id)
    return text if isinstance(text, str) else None


def glob_regex(pattern: str) -> re.Pattern:
    """`**/` any directories, `**` anything, `*` within one path segment, `?` one character."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] in "*?":
            out, i = out + ("[^/]*" if pattern[i] == "*" else "[^/]"), i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def expand(approved, patterns: list[str]) -> list[str]:
    """Approved paths matching any pattern, sorted. `approved` is the manifest's `files` keys."""
    regs = [glob_regex(p) for p in patterns]
    return sorted({p for p in approved if any(r.match(p) for r in regs)})


def incompatible(manifest: dict, tool: str, template_ids: list[str]) -> str | None:
    """A refusal when any selected template reads state this tool does not build; checked before any send."""
    sends = TOOL_STATE[tool]
    for tid in template_ids:
        t = manifest["questions"].get(tid)
        if not isinstance(t, dict):
            return f"unknown or malformed template: {tid}"
        reads = template_state(t)
        if reads not in ACCEPTS[tool]:
            return f"refused: template {tid} reads {', '.join(reads)}, this tool sends {', '.join(sends)}"
    return None


def approve_glob(repo: str, pattern: str) -> dict:
    """`files` entries for tracked files matching the glob that pass the deny-list and screening.

    Prints only; a human reviews and commits. Refused files are listed with the reason."""
    out = subprocess.run(["git", "-C", repo, "ls-files", "-z"], capture_output=True, text=True, env=ask.git_env())
    rx = glob_regex(pattern)
    entries, refused = {}, {}
    for rel in sorted(p for p in out.stdout.split("\0") if p and rx.match(p)):
        if rel == ask.MANIFEST or ask._DENY_NAMES.search(rel) or ask.sensitive(rel):
            refused[rel] = "the manifest itself" if rel == ask.MANIFEST else "denied path"
            continue
        try:
            raw = ask.read_confined(repo, rel)
        except (OSError, ValueError) as e:
            refused[rel] = f"unreadable: {type(e).__name__}"
            continue
        if len(raw) > ask.MAX_FILE_BYTES:
            refused[rel] = "file over 32,000 bytes"
        elif ask.sensitive(raw.decode("utf-8", errors="replace")):
            refused[rel] = "sensitive content"
        else:
            entries[rel] = hashlib.sha256(raw).hexdigest()
    return {"files": entries, "refused": refused}


def approve_prompt(path: str, prompt_id: str) -> dict:
    """A `prompts` entry holding the file's exact text. Never writes the manifest."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip() or ask.sensitive(text):
        return {"refused": {prompt_id: "empty or sensitive prompt text"}}
    return {"prompts": {prompt_id: text}}
