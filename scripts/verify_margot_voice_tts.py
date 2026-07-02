#!/usr/bin/env python3
"""RA-1695 — verify Margot ElevenLabs TTS resolves and synthesises."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.server.margot_voice import resolve_margot_voice_id  # noqa: E402
from swarm import voice_compose as VC  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Margot ElevenLabs TTS smoke check")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--text", default="Margot voice lock verification on the Mac mini.")
    args = parser.parse_args(argv)

    report: dict[str, object] = {
        "voice_id": resolve_margot_voice_id(),
        "api_key_set": bool(os.environ.get("ELEVENLABS_API_KEY", "").strip()),
        "ok": False,
    }

    if not report["api_key_set"]:
        report["error"] = "ELEVENLABS_API_KEY unset"
        report["hint"] = "export from ~/.hermes/.env or op run --"
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"FAIL: {report['error']}", file=sys.stderr)
        return 1

    out = Path("/tmp/margot-voice-tts-smoke.mp3")
    t0 = time.perf_counter()
    written = VC.synthesise_voice(args.text, out_path=out)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    if written is None or not out.exists():
        report["error"] = "synthesise_voice returned None"
        if args.json:
            print(json.dumps(report, indent=2))
        return 1

    report["latency_ms"] = elapsed_ms
    report["audio_bytes"] = out.stat().st_size
    report["audio_path"] = str(out)
    report["ok"] = True

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"OK: voice_id={report['voice_id']} "
            f"bytes={report['audio_bytes']} latency={elapsed_ms}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
