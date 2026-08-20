"""Read a GitHub repo tree + a few files so goal analysis is grounded.

Never pretends the read succeeded. Callers must surface `limitation` when ok is False.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Callable

log = logging.getLogger("pi-ceo.goal_repo_context")

_MAX_TREE = 80
_MAX_FILES = 8
_MAX_FILE_CHARS = 1600
_MAX_EXCERPT = 14_000
FetchFn = Callable[[str, dict[str, str]], tuple[int, str]]

_CODE_SUFFIXES = (
    ".ts", ".tsx", ".js", ".jsx", ".py", ".sql", ".prisma",
    ".json", ".md", ".yml", ".yaml",
)


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "pi-ceo-goal-analyze",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
        log.warning("github fetch failed: %s", type(exc).__name__)
        return 0, ""


def _keywords(goal: str) -> list[str]:
    words = [w.lower() for w in goal.replace("/", " ").replace("-", " ").split() if len(w) > 3]
    return words[:12]


def _score_path(path: str, keywords: list[str]) -> int:
    lower = path.lower()
    score = 0
    for word in keywords:
        if word in lower:
            score += 3
    for hint in ("page.tsx", "route.ts", "layout.tsx", "schema", "supabase", "auth", "prisma"):
        if hint in lower:
            score += 2
    return score


def _blob_paths(tree_json: str) -> list[str]:
    try:
        data = json.loads(tree_json)
    except json.JSONDecodeError:
        return []
    paths: list[str] = []
    for node in data.get("tree") or []:
        if not isinstance(node, dict) or node.get("type") != "blob":
            continue
        path = str(node.get("path") or "")
        if path.endswith(_CODE_SUFFIXES) and "node_modules/" not in path:
            paths.append(path)
    return paths


def _pick_paths(paths: list[str], goal: str) -> list[str]:
    keywords = _keywords(goal)
    ranked = sorted(paths, key=lambda p: _score_path(p, keywords), reverse=True)
    preferred = [p for p in ("README.md", "package.json", "app/layout.tsx") if p in paths]
    picked: list[str] = []
    for path in preferred + ranked:
        if path not in picked:
            picked.append(path)
        if len(picked) >= _MAX_FILES:
            break
    return picked


def _file_excerpt(slug: str, path: str, fetch: FetchFn, headers: dict[str, str]) -> str:
    url = f"https://api.github.com/repos/{slug}/contents/{path}"
    raw_headers = {**headers, "Accept": "application/vnd.github.raw"}
    status, body = fetch(url, raw_headers)
    if status != 200 or not body.strip():
        return ""
    return body[:_MAX_FILE_CHARS]


def gather_repo_context(
    slug: str,
    goal: str,
    *,
    fetch: FetchFn | None = None,
) -> dict[str, Any]:
    """Return {ok, limitation, excerpt}. ok False means do not claim inspection."""
    getter = fetch or _http_get
    headers = _headers()
    tree_url = f"https://api.github.com/repos/{slug}/git/trees/HEAD?recursive=1"
    status, tree_body = getter(tree_url, headers)
    if status != 200:
        reason = "missing GITHUB_TOKEN" if status in (401, 404) and "Authorization" not in headers else f"GitHub HTTP {status or 'error'}"
        return {
            "ok": False,
            "limitation": (
                f"Repo inspection unavailable ({reason}). Drafts are not grounded in "
                f"{slug} source. Confirm paths in the repo before implementing."
            ),
            "excerpt": "",
        }
    paths = _blob_paths(tree_body)
    listing = "\n".join(paths[:_MAX_TREE])
    chunks = [f"## Tree (truncated)\n{listing}"]
    for path in _pick_paths(paths, goal):
        snippet = _file_excerpt(slug, path, getter, headers)
        if snippet:
            chunks.append(f"## {path}\n{snippet}")
    excerpt = "\n\n".join(chunks)[:_MAX_EXCERPT]
    if not excerpt.strip():
        return {
            "ok": False,
            "limitation": f"GitHub returned a tree for {slug} but no file contents could be read.",
            "excerpt": "",
        }
    return {"ok": True, "limitation": "", "excerpt": excerpt}
