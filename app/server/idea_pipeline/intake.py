"""Parse and append short ideas in IDEAS.md. No formatting demanded."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .constants import INTAKE_FILENAME, INTAKE_SKIP_PHRASES, SOURCES

_SOURCE_PREFIX = re.compile(r"^(margot|phill)\s*:\s*", re.IGNORECASE)
_HEADING = re.compile(r"^#{1,6}\s+")


@dataclass(frozen=True)
class RawIdea:
    idea_id: str
    text: str
    source: str
    intake_path: str


def default_intake_path(repo_root: Path) -> Path:
    return repo_root / INTAKE_FILENAME


def idea_id_for(text: str) -> str:
    norm = " ".join(text.lower().split())
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]
    return f"idea-{digest}"


def _is_boilerplate(text: str) -> bool:
    lowered = text.lower()
    if _HEADING.sub("", lowered).strip() == "":
        return True
    return any(phrase in lowered for phrase in INTAKE_SKIP_PHRASES)


def _split_blocks(raw: str) -> list[str]:
    body = raw.replace("\r\n", "\n").strip()
    if not body:
        return []
    if "\n---\n" in f"\n{body}\n":
        return [part.strip() for part in re.split(r"\n---\n", body)]
    return [part.strip() for part in re.split(r"\n\s*\n", body)]


def _source_and_text(block: str) -> tuple[str, str]:
    match = _SOURCE_PREFIX.match(block)
    if match:
        return match.group(1).lower(), block[match.end() :].strip()
    return "phill", block


def parse_ideas_markdown(raw: str, *, intake_path: Path) -> list[RawIdea]:
    ideas: list[RawIdea] = []
    seen: set[str] = set()
    for block in _split_blocks(raw):
        if not block or _is_boilerplate(block):
            continue
        source, text = _source_and_text(block)
        text = " ".join(text.split())
        if not text or _is_boilerplate(text):
            continue
        if source not in SOURCES:
            source = "phill"
        idea_id = idea_id_for(text)
        if idea_id in seen:
            continue
        seen.add(idea_id)
        ideas.append(
            RawIdea(
                idea_id=idea_id,
                text=text,
                source=source,
                intake_path=str(intake_path),
            )
        )
    return ideas


def read_ideas(intake_path: Path) -> list[RawIdea]:
    if not intake_path.is_file():
        return []
    return parse_ideas_markdown(
        intake_path.read_text(encoding="utf-8"),
        intake_path=intake_path,
    )


def append_idea(intake_path: Path, text: str, *, source: str = "phill") -> RawIdea:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        raise ValueError("idea text is empty")
    src = source.strip().lower()
    if src not in SOURCES:
        raise ValueError("source must be phill or margot")
    prefix = f"{src}: " if src == "margot" else ""
    intake_path.parent.mkdir(parents=True, exist_ok=True)
    existing = intake_path.read_text(encoding="utf-8") if intake_path.is_file() else ""
    sep = "" if existing.endswith("\n") or not existing else "\n"
    block = f"{sep}\n---\n\n{prefix}{cleaned}\n"
    if not existing:
        block = (
            "# Ideas\n\n"
            "Drop one to three sentences. No formatting needed.\n"
            "Start a line with `margot:` when Margot writes on Phill's behalf.\n"
            f"{block}"
        )
    intake_path.write_text(existing + block, encoding="utf-8")
    return RawIdea(
        idea_id=idea_id_for(cleaned),
        text=cleaned,
        source=src,
        intake_path=str(intake_path),
    )
