"""scripts/run_doc_parse.py — RA-1995 CLI for pi_ceo_docparser.

Usage:
    python scripts/run_doc_parse.py path/to/doc.pdf
    python scripts/run_doc_parse.py path/to/doc.docx --max-pages 100 --json
    python scripts/run_doc_parse.py interview.txt --tables
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.server.pi_ceo_docparser import parse_document  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Path to PDF / DOCX / TXT")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--json", action="store_true",
                        help="Emit full ParsedDoc as JSON instead of summary")
    parser.add_argument("--tables", action="store_true",
                        help="Print extracted tables (DOCX only)")
    args = parser.parse_args(argv)

    doc = parse_document(args.path, max_pages=args.max_pages)

    if args.json:
        out = asdict(doc)
        print(json.dumps(out, indent=2, default=str))
        return 0 if doc.error is None else 1

    print(f"Source: {doc.source_path}")
    print(f"Type:   {doc.file_type}")
    if doc.error:
        print(f"Error:  {doc.error}")
        if doc.metadata.get("fix"):
            print(f"Fix:    {doc.metadata['fix']}")
        return 1
    print(f"Pages:  {doc.num_pages}")
    print(f"Chars:  {doc.num_chars}")
    if doc.metadata.get("title"):
        print(f"Title:  {doc.metadata['title']}")
    if doc.metadata.get("author"):
        print(f"Author: {doc.metadata['author']}")
    print()
    print("--- BODY (first 1500 chars) ---")
    print(doc.text[:1500])
    if doc.num_chars > 1500:
        print(f"... [{doc.num_chars - 1500} more chars]")
    if args.tables and doc.tables:
        print()
        print(f"--- TABLES ({len(doc.tables)}) ---")
        for i, t in enumerate(doc.tables, start=1):
            print(f"Table {i}: {len(t)} rows × "
                  f"{max((len(r) for r in t), default=0)} cols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
