#!/usr/bin/env python3
"""Discover dense 2nd Brain/Wiki clusters and outside candidate source files."""
from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "into", "within", "will",
    "have", "has", "are", "was", "were", "you", "your", "our", "their", "about",
    "wiki", "source", "sources", "completed", "notes", "note", "file", "files",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 3 and t not in _STOP]


def _read_md(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def scout(brain_root: str | Path, limit: int = 20) -> dict[str, object]:
    root = Path(brain_root)
    wiki_root = root / "Wiki"
    wiki_docs = [p for p in wiki_root.rglob("*.md") if p.is_file()] if wiki_root.exists() else []
    token_docs: dict[str, set[str]] = defaultdict(set)
    doc_tokens: dict[str, Counter[str]] = {}
    for doc in wiki_docs:
        rel = str(doc.relative_to(root))
        counts = Counter(_tokens(_read_md(doc)))
        doc_tokens[rel] = counts
        for token in counts:
            token_docs[token].add(rel)
    clusters = []
    for token, docs in token_docs.items():
        if len(docs) < 1:
            continue
        density = sum(doc_tokens[d][token] for d in docs) * len(docs)
        clusters.append({"name": token, "density": density, "wiki_files": sorted(docs)[:8]})
    clusters.sort(key=lambda item: (-int(item["density"]), str(item["name"])))
    top_tokens = {str(c["name"]) for c in clusters[:10]}
    candidates = []
    search_roots = [root / "Sources", root / "Sources" / "Completed", root.parent]
    seen: set[Path] = set()
    for base in search_roots:
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            if path in seen or (wiki_root.exists() and wiki_root in path.parents):
                continue
            seen.add(path)
            counts = Counter(_tokens(_read_md(path)))
            overlap = sum(counts[t] for t in top_tokens)
            if overlap <= 0:
                continue
            candidates.append({
                "path": str(path.relative_to(root) if root in path.parents else path),
                "score": overlap,
                "matched_clusters": sorted([t for t in top_tokens if counts[t]])[:8],
            })
    candidates.sort(key=lambda item: (-int(item["score"]), str(item["path"])))
    return {"clusters": clusters[:limit], "external_candidates": candidates[:limit]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scout dense Wiki clusters and candidate source notes.")
    parser.add_argument("brain_root")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    print(scout(args.brain_root, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
