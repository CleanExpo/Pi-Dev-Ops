#!/usr/local/bin/python3
"""Plaud Desktop monitor — watches for new recordings or transcription status changes.
Designed to be run as a cronjob. On detection of completed Plaud Notes,
writes trigger file for downstream ingestion into ITR Dimitri."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

CONFIG_PATH = Path("/Users/phillmcgurk/Library/Application Support/Plaud/config.json")
STATE_PATH = Path("/Users/phillmcgurk/.local/state/plaud-monitor/state.json")
TRIGGER_PATH = Path("/tmp/plaud_ready_to_ingest.json")

def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_seen_ids": [], "last_statuses": {}, "last_check": None}

def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))

def main():
    if not CONFIG_PATH.exists():
        print("Plaud config not found — Desktop app not installed?")
        sys.exit(1)
    
    state = load_state()
    config = json.loads(CONFIG_PATH.read_text())
    
    uploads = config.get("uploadHistory", [])
    new_completions = []
    
    for upload in uploads:
        rid = str(upload.get("recordingId", ""))
        status = upload.get("status", "")
        prev_status = state["last_statuses"].get(rid)
        
        if prev_status != status:
            print(f"[{datetime.now(timezone.utc).isoformat()}] Recording {rid}: {prev_status} -> {status}")
            state["last_statuses"][rid] = status
            
            if status in ("ready", "processed", "completed"):
                new_completions.append(upload)
        
        if rid not in state["last_seen_ids"]:
            state["last_seen_ids"].append(rid)
            print(f"  New recording detected: {upload.get('fileName', 'unnamed')} ({rid})")
    
    if new_completions:
        TRIGGER_PATH.write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recordings": new_completions
        }, indent=2))
        print(f"  WRITTEN TRIGGER: {TRIGGER_PATH}")
        print(f"  Run: cd /Users/phillmcgurk/ITR\ Dimitri && hermes-plaud-ingest")
    
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

if __name__ == "__main__":
    main()
