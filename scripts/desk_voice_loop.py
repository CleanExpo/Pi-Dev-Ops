#!/usr/bin/env python3
"""Margot desk voice loop — mic → STT → Hermes → ElevenLabs TTS → speakers.

RA-1694/1696. Uses locked Margot ElevenLabs voice (not edge-tts / Voicebox).

Usage:
  python scripts/desk_voice_loop.py --mode ptt   # requires external mic (USB headset)
  python scripts/desk_voice_loop.py --mode vad   # requires external mic
  python scripts/desk_voice_loop.py --mode text  # no mic — type at prompt, hear reply

Mac mini has no built-in microphone. PTT/VAD need a USB headset or desk mic.
For voice-in without local hardware, use Telegram voice notes (RA-1886) or
iPhone Shortcut path (RA-1698). Text mode validates Hermes + ElevenLabs playback.

Env: ELEVENLABS_API_KEY, optional MARGOT_ELEVENLABS_VOICE_ID override.
Hermes: http://localhost:8642/v1 (api_server platform).
STT: faster-whisper in ~/.hermes/hermes-agent/.venv (see verify_margot_voice_stt.py).
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from swarm import voice_compose as VC  # noqa: E402

HERMES_BASE = os.environ.get("HERMES_OPENAI_BASE", "http://localhost:8642/v1")
HERMES_MODEL = os.environ.get("HERMES_OPENAI_MODEL", "empire")
PI_CEO_BASE = os.environ.get(
    "PI_CEO_API_URL", "https://pi-dev-ops-production.up.railway.app"
).rstrip("/")
PI_CEO_SECRET = os.environ.get("PI_CEO_API_KEY") or os.environ.get("TAO_WEBHOOK_SECRET")
DESK_CHAT_ID = os.environ.get("MARGOT_DESK_CHAT_ID", "8792816988")
HERMES_API_KEY = (
    os.environ.get("API_SERVER_KEY")
    or os.environ.get("HERMES_OPENAI_API_KEY")
    or "local"
)
SAMPLE_RATE = 16_000
CHANNELS = 1
SILENCE_THRESHOLD = 1.5
PTT_KEY = " "
LOG_PATH = Path.home() / "bron-workspace" / "voice" / "loop.log"
PROFILE_PATH = Path.home() / "bron-workspace" / "voice" / "profile-locked.md"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("desk-voice-loop")


def _require_package(name: str, import_name: str) -> object:
    import importlib

    try:
        return importlib.import_module(import_name)
    except ImportError:
        print(f"[loop] Missing: {import_name}  →  pip install {name}", file=sys.stderr)
        sys.exit(1)


def _check_profile() -> None:
    if not PROFILE_PATH.exists():
        print(
            f"[loop] Missing voice profile: {PROFILE_PATH}\n"
            "       Run RA-1695 lock (ElevenLabs SSOT).",
            file=sys.stderr,
        )
        sys.exit(1)


class WhisperSTT:
    def __init__(self, python: Path | None = None) -> None:
        self._python = python or Path.home() / ".hermes/hermes-agent/.venv/bin/python"
        fw = _require_package("faster-whisper", "faster_whisper")
        log.info("Loading Whisper model (base.en)…")
        self._model = fw.WhisperModel("base.en", device="cpu", compute_type="int8")

    def transcribe(self, audio_bytes: bytes) -> str:
        sf = _require_package("soundfile", "soundfile")
        buf = io.BytesIO(audio_bytes)
        audio, _ = sf.read(buf, dtype="float32")
        segments, _ = self._model.transcribe(audio, beam_size=5, language="en")
        return " ".join(s.text.strip() for s in segments).strip()


class MargotElevenLabsTTS:
    def synthesise(self, text: str) -> Path:
        out_dir = _REPO / ".harness" / "swarm" / "voice" / "desk-loop"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"turn-{int(time.time())}.mp3"
        written = VC.synthesise_voice(text, out_path=out_path)
        if written is None:
            raise RuntimeError("ElevenLabs synthesis failed — check ELEVENLABS_API_KEY")
        return written


def play_audio(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["afplay", str(path)], check=True)
        return
    sd = _require_package("sounddevice", "sounddevice")
    sf = _require_package("soundfile", "soundfile")
    data, samplerate = sf.read(str(path), dtype="float32")
    sd.play(data, samplerate=samplerate, blocking=True)


class HermesSession:
    def __init__(self) -> None:
        self._history: list[dict[str, str]] = []
        try:
            from openai import OpenAI

            self._client = OpenAI(base_url=HERMES_BASE, api_key=HERMES_API_KEY)
        except ImportError:
            self._client = None

    def _chat_piceo(self, user_text: str) -> str:
        if not PI_CEO_SECRET:
            raise RuntimeError("PI_CEO_API_KEY / TAO_WEBHOOK_SECRET not set")
        import urllib.request

        body = json.dumps(
            {
                "chat_id": DESK_CHAT_ID,
                "user_text": user_text,
                "tenant_id": "pi-ceo",
            }
        ).encode()
        req = urllib.request.Request(
            f"{PI_CEO_BASE}/api/margot/turn",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Pi-CEO-Secret": PI_CEO_SECRET,
            },
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = json.loads(r.read())
        return str(payload.get("reply") or "")

    def chat(self, user_text: str) -> str:
        self._history.append({"role": "user", "content": user_text})
        reply = ""
        try:
            if self._client:
                resp = self._client.chat.completions.create(
                    model=HERMES_MODEL, messages=self._history, stream=False
                )
                reply = resp.choices[0].message.content or ""
            else:
                import urllib.request

                body = json.dumps({"model": HERMES_MODEL, "messages": self._history}).encode()
                req = urllib.request.Request(
                    f"{HERMES_BASE}/chat/completions",
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {HERMES_API_KEY}",
                    },
                )
                with urllib.request.urlopen(req, timeout=60) as r:
                    reply = json.loads(r.read())["choices"][0]["message"]["content"]
        except Exception as exc:
            log.warning("Local Hermes failed (%s), falling back to Pi-CEO margot_turn", exc)
            reply = self._chat_piceo(user_text)
        self._history.append({"role": "assistant", "content": reply})
        return reply


def record_ptt() -> bytes | None:
    sd = _require_package("sounddevice", "sounddevice")
    sf = _require_package("soundfile", "soundfile")
    _require_package("numpy", "numpy")
    _require_package("pynput", "pynput.keyboard")
    import threading
    from pynput.keyboard import Listener as KbListener

    print("  Hold SPACEBAR to speak, release to send…")
    frames: list[bytes] = []
    stop_event = threading.Event()
    held = threading.Event()

    def on_press(key):
        try:
            if key.char == PTT_KEY or str(key) == "Key.space":
                held.set()
        except AttributeError:
            if str(key) == "Key.space":
                held.set()

    def on_release(key):
        try:
            if key.char == PTT_KEY or str(key) == "Key.space":
                stop_event.set()
        except AttributeError:
            if str(key) == "Key.space":
                stop_event.set()

    held.wait(timeout=30)
    if not held.is_set():
        return None

    print("  [recording…]", end=" ", flush=True)
    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16") as stream:
        listener = KbListener(on_press=on_press, on_release=on_release)
        listener.start()
        while not stop_event.is_set():
            data, _ = stream.read(1024)
            frames.append(bytes(data))
        listener.stop()
    print("[done]")
    import numpy as np

    raw = b"".join(frames)
    audio = np.frombuffer(raw, dtype="int16").astype("float32") / 32768.0
    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE, format="WAV")
    return buf.getvalue()


def _read_text_turn() -> str | None:
    try:
        line = input("  You: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return line or None


def run_loop(mode: str) -> None:
    _check_profile()
    print(f"\nMargot desk voice loop — mode={mode} (ElevenLabs TTS)")
    if mode == "text":
        print("   Type a message and press Enter. Ctrl+C or empty line to quit.\n")
    else:
        print("   Ctrl+C to quit.\n")

    stt = None
    if mode != "text":
        print("  Loading speech model…", flush=True)
        stt = WhisperSTT()
    tts = MargotElevenLabsTTS()
    hermes = HermesSession()

    while True:
        t_start = time.monotonic()
        try:
            if mode == "text":
                transcript = _read_text_turn()
                if transcript is None:
                    print("\nBye.")
                    return
            else:
                audio_bytes = record_ptt() if mode in ("ptt", "wake") else None
                if not audio_bytes:
                    continue
                try:
                    transcript = stt.transcribe(audio_bytes)  # type: ignore[union-attr]
                except Exception as exc:
                    log.error("STT failed: %s", exc)
                    print("  [couldn't hear you — try again]")
                    continue
                if not transcript.strip():
                    print("  [no speech detected]")
                    continue
                print(f"  You:    {transcript}")
        except KeyboardInterrupt:
            print("\nBye.")
            return
        try:
            reply = hermes.chat(transcript)
        except Exception as exc:
            log.error("Hermes failed: %s", exc)
            reply = "Hermes isn't responding right now."
        print(f"  Margot: {reply}")

        try:
            audio_path = tts.synthesise(reply)
            play_audio(audio_path)
        except Exception as exc:
            log.error("TTS/playback failed: %s", exc)
            print(f"  [TTS error: {exc}]")
            continue

        total = round(time.monotonic() - t_start, 3)
        log.info("turn complete total_s=%s", total)
        print(f"  [turn: {total}s]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Margot desk voice loop (ElevenLabs)")
    parser.add_argument(
        "--mode",
        choices=["ptt", "vad", "wake", "text"],
        default="ptt",
        help="ptt/vad/wake need external mic; text = keyboard in, speakers out",
    )
    args = parser.parse_args()
    try:
        run_loop(args.mode)
    except KeyboardInterrupt:
        print("\nLoop stopped.")


if __name__ == "__main__":
    main()
