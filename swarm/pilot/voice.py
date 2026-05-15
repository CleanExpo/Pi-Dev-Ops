"""Voice pipeline — getFile download + Transcriber Protocol + routing.

Per ADR 003: Discuss verb triggers a voice-reply branch. The concrete
transcription provider is gated on a Phill call (Whisper vs Deepgram);
v1 ships StubTranscriber raising NotImplementedError so the call-site
contract is wired. Provider pick deferred to v1.1 ADR 004.
"""
import os
from pathlib import Path
from typing import Protocol

import requests


class Transcriber(Protocol):
    def transcribe(self, audio_bytes: bytes) -> str: ...


class StubTranscriber:
    def transcribe(self, audio_bytes: bytes) -> str:
        raise NotImplementedError(
            "transcription provider not configured — see v1.1 ADR 004 for provider pick"
        )


def download_voice_file(file_id: str, dest_dir: Path) -> Path:
    """Download a Telegram voice file to dest_dir. Returns the local Path."""
    token = os.environ["PILOT_BOT_TOKEN"]
    info_url = f"https://api.telegram.org/bot{token}/getFile"
    r = requests.get(info_url, params={"file_id": file_id}, timeout=10)
    r.raise_for_status()
    payload = r.json()
    if not payload.get("ok"):
        raise RuntimeError(f"getFile failed: {payload}")
    file_path = payload["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    r2 = requests.get(file_url, timeout=30)
    r2.raise_for_status()
    suffix = Path(file_path).suffix or ".oga"
    out = Path(dest_dir) / f"{file_id}{suffix}"
    out.write_bytes(r2.content)
    return out


def route_voice_reply(*, suggestion_id: int, transcript: str,
                      tenant_slug: str, memory) -> None:
    """Persist a voice reply transcript for a suggestion."""
    memory.record_voice_reply(
        suggestion_id=suggestion_id,
        transcript=transcript,
        tenant_slug=tenant_slug,
    )
