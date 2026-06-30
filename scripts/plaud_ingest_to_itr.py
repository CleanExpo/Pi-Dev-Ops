#!/usr/bin/env python3
"""Ingest completed Plaud recording into ITR Dimitri vision system.
Triggered by cronjob when Plaud Desktop config shows status=ready."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

PLAUD_DIR = Path("/Users/phillmcgurk/Library/Application Support/Plaud")
ITR_DIR = Path("/Users/phillmcgurk/ITR Dimitri")
VISION_PATH = ITR_DIR / "DUNCAN-LIVING-VISION.md"

def main():
    trigger_path = Path("/tmp/plaud_ingest_trigger.json")
    if not trigger_path.exists():
        print("No trigger file found — Plaud Notes not ready yet.")
        sys.exit(0)
    
    trigger = json.loads(trigger_path.read_text())
    recordings = trigger.get("recordings", [])
    
    if not recordings:
        print("Trigger file empty.")
        sys.exit(0)
    
    for rec in recordings:
        rid = rec.get("recordingId")
        file_name = rec.get("fileName", "unnamed")
        file_id = rec.get("fileId", "")
        
        print(f"\n=== Ingesting Plaud recording: {file_name} ({rid}) ===")
        
        # Build vision entry
        entry = f"""
## Voice Memo — {file_name}

- **Source**: Plaud AI Recorder (ITR-Button)
- **Recording ID**: `{rid}`
- **File ID**: `{file_id}`
- **Ingested**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
- **Status**: Plaud Notes generated

### Plaud Notes Summary
[To be populated when transcript API accessible]

### Raw Audio
- Location: `{PLAUD_DIR}/ogg-discard/output-{rid}.ogg`
- Duration: ~15s (pending precise measurement)

### Action Items
[To be extracted from transcript]

---
"""
        
        # Append to vision document
        if VISION_PATH.exists():
            content = VISION_PATH.read_text()
            # Insert before the last section or append
            if "## Voice Memo" not in content:
                content = content.rstrip() + "\n\n" + entry
                VISION_PATH.write_text(content)
                print(f"  Appended to {VISION_PATH}")
            else:
                print(f"  Entry already exists in vision doc — skipping duplicate")
        else:
            print(f"  WARNING: {VISION_PATH} not found")
    
    # Clean up trigger
    trigger_path.unlink()
    print("\nIngestion complete. Trigger file cleaned up.")

if __name__ == "__main__":
    main()
