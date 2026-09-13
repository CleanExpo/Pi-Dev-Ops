"""Read-only wiki_pages access against the Unite-Group Supabase project.

wiki_pages lives in project lksfwktwtmyznckodsau. Railway already holds those
credentials as ``UGO_SUPABASE_*``; Vercel historically looked only for
``SUPABASE_UNITE_GROUP_*`` and 503'd. This helper accepts both pairs and never
falls back to Pi CEO's ``SUPABASE_SERVICE_ROLE_KEY`` (wrong project).
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Optional

log = logging.getLogger("pi-ceo.unite_group_wiki")

DEFAULT_URL = "https://lksfwktwtmyznckodsau.supabase.co"
WIKI_PAGES_LIMIT = 1000
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_EMPTY_GRAPH = {
    "nodes": [],
    "edges": [],
    "pageCount": 0,
    "lastSync": None,
    "truncated": False,
    "edgeCount": 0,
}


def _first_env(*names: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def resolve_creds() -> tuple[str, Optional[str]]:
    """Return (url, key). URL defaults; key is None when neither alias is set."""
    url = _first_env("SUPABASE_UNITE_GROUP_URL", "UGO_SUPABASE_URL") or DEFAULT_URL
    key = _first_env("SUPABASE_UNITE_GROUP_SERVICE_KEY", "UGO_SUPABASE_SERVICE_KEY")
    return url.rstrip("/"), (key or None)


def parse_wiki_links(content: str) -> list[str]:
    out: list[str] = []
    for raw in _WIKILINK_RE.findall(content or ""):
        target = raw.split("|")[0].split("#")[0].strip()
        if target:
            out.append(target)
    return out


def _target_keys(target: str) -> list[str]:
    lower = target.lower()
    keys = [lower]
    slash = lower.rfind("/")
    if slash != -1 and slash < len(lower) - 1:
        keys.append(lower[slash + 1 :])
    return keys


def _resolve_map(pages: list[dict[str, Any]]) -> dict[str, str]:
    resolve: dict[str, str] = {}
    for page in pages:
        title_key = str(page.get("title") or "").lower().strip()
        if title_key and title_key not in resolve:
            resolve[title_key] = str(page["id"])
    for page in pages:
        resolve[str(page["id"]).lower().strip()] = str(page["id"])
    return resolve


def _collect_edges(
    pages: list[dict[str, Any]], resolve: dict[str, str]
) -> tuple[list[dict[str, str]], dict[str, int]]:
    degree = {str(page["id"]): 0 for page in pages}
    seen: set[str] = set()
    edges: list[dict[str, str]] = []
    for page in pages:
        source = str(page["id"])
        for target in parse_wiki_links(str(page.get("content") or "")):
            resolved = next((resolve[k] for k in _target_keys(target) if k in resolve), None)
            if not resolved or resolved == source:
                continue
            dedupe = f"{source}\0{resolved}"
            if dedupe in seen:
                continue
            seen.add(dedupe)
            edges.append({"source": source, "target": resolved})
            degree[source] = degree.get(source, 0) + 1
            degree[resolved] = degree.get(resolved, 0) + 1
    return edges, degree


def build_wiki_graph(pages: list[dict[str, Any]]) -> dict[str, Any]:
    resolve = _resolve_map(pages)
    edges, degree = _collect_edges(pages, resolve)
    last_sync: Optional[str] = None
    for page in pages:
        updated = page.get("updated_at")
        if isinstance(updated, str) and (last_sync is None or updated > last_sync):
            last_sync = updated
    nodes = [
        {
            "id": str(page["id"]),
            "title": page.get("title") or "",
            "slug": str(page["id"]),
            "tags": page.get("tags") or [],
            "degree": degree.get(str(page["id"]), 0),
        }
        for page in pages
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "pageCount": len(pages),
        "lastSync": last_sync,
    }


def graph_payload(pages: list[dict[str, Any]]) -> dict[str, Any]:
    graph = build_wiki_graph(pages)
    truncated = len(pages) >= WIKI_PAGES_LIMIT
    graph["truncated"] = truncated
    graph["edgeCount"] = len(graph["edges"])
    if truncated:
        graph["warning"] = (
            f"Only the first {WIKI_PAGES_LIMIT} pages were read, so this graph is "
            "incomplete. Nodes and edges beyond the cap are missing, not absent."
        )
    return graph


def empty_graph(reason: str) -> dict[str, Any]:
    payload = dict(_EMPTY_GRAPH)
    payload["source"] = "unconfigured"
    payload["reason"] = reason
    return payload


def fetch_wiki_pages() -> tuple[Optional[list[dict[str, Any]]], Optional[str]]:
    url, key = resolve_creds()
    if not key:
        return None, "Unite-Group Supabase key is not configured"
    endpoint = (
        f"{url}/rest/v1/wiki_pages"
        f"?select=id,title,tags,content,updated_at&limit={WIKI_PAGES_LIMIT}"
    )
    req = urllib.request.Request(
        endpoint,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        log.warning("wiki_pages read failed: HTTP %s", exc.code)
        return None, f"wiki_pages read failed (HTTP {exc.code})"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        log.warning("wiki_pages read failed: transport or parse error")
        return None, "wiki_pages read failed"
    if not isinstance(rows, list):
        return None, "wiki_pages read returned a non-list"
    return rows, None
