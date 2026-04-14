#!/usr/bin/env python3
"""
.harness/lessons_search.py — Semantic search over lessons.jsonl using ChromaDB.

RA-927: ChromaDB + all-MiniLM-L6-v2 (ONNX, no PyTorch required) + HyDE.

Usage:
  python .harness/lessons_search.py "Railway deployment restart"
  python .harness/lessons_search.py "Railway deployment restart" --n 10
  python .harness/lessons_search.py --index-only    # re-index without searching
  python .harness/lessons_search.py --stats         # show collection stats

Requirements:
  pip install chromadb

The ONNX model (~90MB) is downloaded on first use and cached under
~/.cache/chroma/onnx_models/ — this is local-only, never runs on Railway.

ChromaDB persists to .harness/chroma/ (gitignored). Re-run --index-only
after adding new lessons to keep the index fresh.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[1]
_HARNESS   = _REPO_ROOT / ".harness"
_LESSONS   = _HARNESS / "lessons.jsonl"
_CHROMA    = _HARNESS / "chroma"
_COLLECTION = "lessons"


def _get_collection():
    """Open (or create) the ChromaDB collection with the default ONNX embedding."""
    try:
        import chromadb
    except ImportError:
        sys.exit(
            "chromadb not installed. Run: pip install chromadb\n"
            "(Uses onnxruntime under the hood — no PyTorch needed.)"
        )
    client = chromadb.PersistentClient(path=str(_CHROMA))
    # DefaultEmbeddingFunction uses all-MiniLM-L6-v2 via ONNX (no torch)
    return client.get_or_create_collection(_COLLECTION)


def _load_lessons() -> list[dict]:
    """Read lessons.jsonl and return a list of dicts."""
    if not _LESSONS.exists():
        return []
    entries = []
    with open(_LESSONS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def index(force: bool = False) -> int:
    """Upsert all lessons.jsonl entries into ChromaDB. Returns upserted count."""
    lessons = _load_lessons()
    if not lessons:
        print("No lessons found in", _LESSONS)
        return 0

    col = _get_collection()
    existing = set(col.get()["ids"])

    docs, ids, metas = [], [], []
    for i, entry in enumerate(lessons):
        lid = entry.get("id") or f"lesson-{i}"
        if not force and lid in existing:
            continue
        docs.append(entry.get("lesson", ""))
        ids.append(lid)
        metas.append({
            "ts":       entry.get("ts", ""),
            "source":   entry.get("source", ""),
            "category": entry.get("category", ""),
            "severity": entry.get("severity", "info"),
        })

    if docs:
        col.upsert(documents=docs, ids=ids, metadatas=metas)
        print(f"Indexed {len(docs)} new lesson(s) into {_CHROMA}")
    else:
        print(f"All {len(lessons)} lessons already indexed.")

    return len(docs)


def search(query: str, n: int = 5, use_hyde: bool = True) -> list[dict]:
    """
    Semantic search over lessons.

    HyDE (Hypothetical Document Embeddings): generates a synthetic lesson
    for the query first, then embeds that, improving recall for vague questions.
    HyDE requires ANTHROPIC_API_KEY; falls back to direct embedding if missing.
    """
    col = _get_collection()
    if col.count() == 0:
        index()

    search_text = query
    if use_hyde:
        search_text = _hyde(query) or query

    results = col.query(
        query_texts=[search_text],
        n_results=min(n, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "lesson":   doc,
            "score":    round(1 - dist, 3),
            "category": meta.get("category", ""),
            "source":   meta.get("source", ""),
            "ts":       meta.get("ts", ""),
            "severity": meta.get("severity", "info"),
        })
    return hits


def _hyde(query: str) -> str | None:
    """
    Generate a hypothetical lesson for the query using Claude Haiku.
    Falls back to None (disabling HyDE) if API key is not available.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=80,
            messages=[{
                "role": "user",
                "content": (
                    f"Write a single concise engineering lesson (one sentence, max 30 words) "
                    f"that would answer or relate to this topic: {query}"
                ),
            }],
        )
        text = resp.content[0].text.strip() if resp.content else ""
        return text or None
    except Exception:
        return None


def stats() -> None:
    """Print collection stats."""
    col = _get_collection()
    print(f"Collection '{_COLLECTION}' at {_CHROMA}")
    print(f"  Documents: {col.count()}")
    print(f"  Lessons file: {_LESSONS} ({_load_lessons().__len__()} lines)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic search over Pi CEO lessons.jsonl")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--n", type=int, default=5, help="Number of results (default 5)")
    parser.add_argument("--no-hyde", action="store_true", help="Disable HyDE (direct embedding)")
    parser.add_argument("--index-only", action="store_true", help="Re-index without searching")
    parser.add_argument("--force-reindex", action="store_true", help="Force re-index all lessons")
    parser.add_argument("--stats", action="store_true", help="Show collection stats")
    args = parser.parse_args()

    if args.stats:
        stats()
        return

    if args.index_only or args.force_reindex:
        index(force=args.force_reindex)
        return

    if not args.query:
        parser.print_help()
        return

    results = search(args.query, n=args.n, use_hyde=not args.no_hyde)
    if not results:
        print("No results found. Run --index-only to populate the index.")
        return

    print(f"\nTop {len(results)} lessons for: \"{args.query}\"\n")
    for i, r in enumerate(results, 1):
        severity_marker = "⚠️ " if r["severity"] == "warn" else "  "
        print(f"{i}. [{r['score']:.3f}] {severity_marker}{r['lesson']}")
        print(f"   category={r['category']} source={r['source']}")
        print()


if __name__ == "__main__":
    main()
