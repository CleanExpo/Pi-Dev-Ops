"""
fetch_anthropic_docs.py — Daily Anthropic developer docs pull.

Fetches key pages from docs.anthropic.com and stores them as markdown
in .harness/anthropic-docs/. Run via cron at 5:50am AEST daily (RA-466).

Usage:
    python scripts/fetch_anthropic_docs.py
    python scripts/fetch_anthropic_docs.py --dry-run
"""
import argparse, json, os, re, sys, time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# Docs to fetch — ordered by relevance to Pi Dev Ops
DOCS = [
    {
        "key": "claude-code-overview",
        "url": "https://docs.anthropic.com/en/docs/claude-code/overview",
        "title": "Claude Code Overview",
    },
    {
        "key": "claude-code-cli-reference",
        "url": "https://docs.anthropic.com/en/docs/claude-code/cli-reference",
        "title": "Claude Code CLI Reference",
    },
    {
        "key": "mcp-overview",
        "url": "https://docs.anthropic.com/en/docs/mcp",
        "title": "Model Context Protocol Overview",
    },
    {
        "key": "tool-use",
        "url": "https://docs.anthropic.com/en/docs/tool-use",
        "title": "Tool Use (Function Calling)",
    },
    {
        "key": "models-overview",
        "url": "https://docs.anthropic.com/en/docs/models-overview",
        "title": "Models Overview",
    },
    {
        "key": "api-reference",
        "url": "https://docs.anthropic.com/en/api/getting-started",
        "title": "API Reference — Getting Started",
    },
]

_HEADERS = {
    "User-Agent": "Pi-Dev-Ops/3.0 docs-fetcher (automated; contact: pi-dev-ops)",
    "Accept": "text/html,application/xhtml+xml",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\n{3,}")


def _strip_html(html: str) -> str:
    """Minimal HTML → plain text (no external deps)."""
    text = _TAG_RE.sub(" ", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    lines = [l.strip() for l in text.splitlines()]
    text = "\n".join(l for l in lines if l)
    return _WHITESPACE_RE.sub("\n\n", text)


def fetch_page(url: str, timeout: int = 15) -> str | None:
    try:
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except URLError as e:
        print(f"  WARN: fetch failed for {url}: {e}", file=sys.stderr)
        return None


def run(dry_run: bool = False) -> dict:
    project_root = Path(__file__).parent.parent
    out_dir = project_root / ".harness" / "anthropic-docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    results = {"timestamp": timestamp, "fetched": [], "failed": []}

    for doc in DOCS:
        key = doc["key"]
        title = doc["title"]
        url = doc["url"]
        print(f"  Fetching: {title} ({url})")

        if dry_run:
            results["fetched"].append(key)
            continue

        html = fetch_page(url)
        if html is None:
            results["failed"].append(key)
            continue

        text = _strip_html(html)
        out_path = out_dir / f"{key}.md"
        out_path.write_text(
            f"# {title}\n\n"
            f"**Source:** {url}\n"
            f"**Fetched:** {timestamp}\n\n"
            f"---\n\n"
            f"{text[:20000]}\n",
            encoding="utf-8",
        )
        results["fetched"].append(key)
        print(f"    Saved {out_path.name} ({len(text):,} chars)")
        time.sleep(1)  # polite crawl delay

    # Write index
    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n  Done: {len(results['fetched'])} fetched, {len(results['failed'])} failed")
    print(f"  Index: {index_path}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Anthropic developer docs")
    parser.add_argument("--dry-run", action="store_true", help="Skip actual HTTP fetches")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run)
    sys.exit(0 if not result["failed"] else 1)
