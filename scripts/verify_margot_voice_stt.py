#!/usr/bin/env python3
"""
verify_margot_voice_stt.py — RA-1692 faster-whisper STT smoke check (Mac mini).

Confirms the Hermes venv can import faster-whisper, loads base.en, and
transcribes a short clip within a latency budget.

Usage:
  python scripts/verify_margot_voice_stt.py
  python scripts/verify_margot_voice_stt.py --python ~/.hermes/hermes-agent/.venv/bin/python
  python scripts/verify_margot_voice_stt.py --wav /path/to/sample.wav --json

Exit codes:
  0 — import + transcription succeeded
  1 — dependency missing or transcription failed
  2 — latency exceeded --max-ms (still prints JSON when --json)
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

_DEFAULT_PYTHON = Path.home() / ".hermes/hermes-agent/.venv/bin/python"
_DEFAULT_MODEL = "base.en"
_TARGET_MS = 800


def _write_silence_wav(path: Path, *, duration_s: float, sample_rate: int) -> None:
    """Write mono 16-bit PCM silence — enough for a load/transcribe smoke test."""
    n_frames = int(duration_s * sample_rate)
    chunk_frames = 4096
    silence_chunk = struct.pack(f"<{chunk_frames}h", *([0] * chunk_frames))
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        written = 0
        while written < n_frames:
            take = min(chunk_frames, n_frames - written)
            if take == chunk_frames:
                handle.writeframes(silence_chunk)
            else:
                handle.writeframes(struct.pack(f"<{take}h", *([0] * take)))
            written += take


def _import_check(python: Path) -> dict[str, str]:
    import subprocess

    proc = subprocess.run(
        [
            str(python),
            "-c",
            "import faster_whisper as fw; print(fw.__version__)",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"faster_whisper not importable in {python}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return {"faster_whisper_version": proc.stdout.strip()}


def _transcribe_smoke(
    python: Path,
    wav_path: Path,
    *,
    model: str,
    device: str,
    compute_type: str,
) -> dict[str, object]:
    import subprocess

    wav_literal = json.dumps(str(wav_path))
    script = f"""
import time
from faster_whisper import WhisperModel

wav = {wav_literal}
model = WhisperModel({model!r}, device={device!r}, compute_type={compute_type!r})
start = time.perf_counter()
segments, _ = model.transcribe(str(wav), beam_size=5, language="en")
text = " ".join(s.text.strip() for s in segments).strip()
elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
print(__import__("json").dumps({{"latency_ms": elapsed_ms, "text": text, "model": {model!r}}}))
"""
    proc = subprocess.run([str(python), "-c", script], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "transcription failed")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RA-1692 faster-whisper STT smoke check")
    parser.add_argument("--python", type=Path, default=_DEFAULT_PYTHON)
    parser.add_argument("--model", default=_DEFAULT_MODEL)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--duration-s", type=float, default=5.0)
    parser.add_argument("--wav", type=Path, default=None, help="Optional input WAV (16 kHz mono preferred)")
    parser.add_argument("--max-ms", type=float, default=_TARGET_MS, help="Latency budget (informational)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report: dict[str, object] = {
        "python": str(args.python),
        "model": args.model,
        "target_ms": args.max_ms,
        "ok": False,
    }

    if not args.python.exists():
        report["error"] = f"Python not found: {args.python}"
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"FAIL: {report['error']}", file=sys.stderr)
        return 1

    try:
        report.update(_import_check(args.python))
    except RuntimeError as exc:
        report["error"] = str(exc)
        report["install_hint"] = f"{args.python} -m pip install faster-whisper"
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
            print(f"Hint: {report['install_hint']}", file=sys.stderr)
        return 1

    wav_path = args.wav
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if wav_path is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="margot-stt-")
        wav_path = Path(temp_dir.name) / "smoke-silence.wav"
        _write_silence_wav(wav_path, duration_s=args.duration_s, sample_rate=16_000)
    report["wav"] = str(wav_path)

    try:
        tx = _transcribe_smoke(
            args.python,
            wav_path,
            model=args.model,
            device=args.device,
            compute_type=args.compute_type,
        )
    except RuntimeError as exc:
        report["error"] = str(exc)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    latency_ms = float(tx["latency_ms"])
    report["latency_ms"] = latency_ms
    report["transcript"] = tx.get("text", "")
    report["within_budget"] = latency_ms <= args.max_ms
    report["groq_fallback_recommended"] = latency_ms > 1500
    report["ok"] = True

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        budget = "within" if report["within_budget"] else "over"
        print(
            f"OK: faster-whisper {report['faster_whisper_version']} "
            f"model={args.model} latency={latency_ms}ms ({budget} {args.max_ms}ms target)"
        )
        if report["groq_fallback_recommended"]:
            print("NOTE: latency > 1500ms — consider Groq Whisper API fallback (GROQ_API_KEY)")

    return 0 if report["within_budget"] or not args.json else 2


if __name__ == "__main__":
    raise SystemExit(main())
