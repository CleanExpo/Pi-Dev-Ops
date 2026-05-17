#!/usr/bin/env python3
"""Sync 2nd Brain wiki pages to Supabase wiki_pages table."""
import json, os, re, sys, urllib.request
from pathlib import Path

WIKI_DIR = Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"
SUPABASE_URL = "https://lksfwktwtmyznckodsau.supabase.co"

def get_service_key():
    env_file = Path("/tmp/ug-env-prod.local")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

def upsert_page(key, page_id, title, content, tags):
    payload = json.dumps({
        "id": page_id,
        "title": title,
        "content": content[:50000],
        "tags": tags,
        "word_count": len(content.split()),
    }).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/wiki_pages",
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

SKIP = {"log.md", "index.md", "MEMORY.md"}

def main():
    key = get_service_key()
    if not key:
        print("ERROR: no service key"); sys.exit(1)

    pages = list(WIKI_DIR.rglob("*.md"))
    synced = 0
    for p in pages:
        if p.name in SKIP:
            continue
        content = p.read_text(encoding="utf-8")
        # Extract title from first H1 or filename
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else p.stem.replace("-", " ").title()
        page_id = str(p.relative_to(WIKI_DIR).with_suffix(""))
        # Extract tags from content (wiki links [[tag]])
        tags = list(set(re.findall(r'\[\[([^\]]+)\]\]', content)))[:10]
        try:
            upsert_page(key, page_id, title, content, tags)
            print(f"  + {page_id}")
            synced += 1
        except Exception as e:
            print(f"  x {page_id}: {e}")

    print(f"\nSynced {synced}/{len(pages)} wiki pages to Supabase")

if __name__ == "__main__":
    main()
