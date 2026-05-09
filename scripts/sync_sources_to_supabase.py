#!/usr/bin/env python3
"""Sync 2nd Brain completed sources metadata to Supabase wiki_sources table."""
import json, os, re, sys, urllib.request
from pathlib import Path

SOURCES_DIR = Path.home() / "2nd Brain" / "2nd Brain" / "Sources" / "Completed"
SUPABASE_URL = "https://lksfwktwtmyznckodsau.supabase.co"

def get_service_key():
    env_file = Path("/tmp/ug-env-prod.local")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

def parse_frontmatter_title(content):
    """Extract title from YAML frontmatter or first H1."""
    fm = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm:
        m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm.group(1), re.MULTILINE)
        if m:
            return m.group(1).strip().strip('"\'')
    h1 = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if h1:
        return h1.group(1).strip()
    return None

def upsert_source(key, source_id, title):
    payload = json.dumps({
        "id": source_id,
        "title": title,
        "status": "completed",
    }).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/wiki_sources",
        data=payload,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')[:80]

def main():
    key = get_service_key()
    if not key:
        print("ERROR: no service key"); sys.exit(1)

    pages = list(SOURCES_DIR.glob("*.md"))
    synced = 0
    for p in pages:
        content = p.read_text(encoding="utf-8", errors="replace")
        title = parse_frontmatter_title(content) or p.stem
        source_id = slugify(p.stem)
        try:
            upsert_source(key, source_id, title)
            print(f"  + {source_id[:60]}")
            synced += 1
        except Exception as e:
            print(f"  x {p.stem[:40]}: {e}")

    print(f"\nSynced {synced}/{len(pages)} sources to Supabase")

if __name__ == "__main__":
    main()
