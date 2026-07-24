"""Telegram-safe chunking helpers extracted from the six-pager assembler."""
from __future__ import annotations

import re

TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_CHUNK_BUDGET = TELEGRAM_MESSAGE_LIMIT - 32
_SECTION_BOUNDARY = re.compile(r"^(?=\d+\.\s+)", re.MULTILINE)


def chunk_for_telegram(
    brief: str, *, max_chars: int = TELEGRAM_CHUNK_BUDGET,
) -> list[str]:
    if len(brief) <= max_chars:
        return [brief]
    sections = _split_on_section_boundary(brief)
    chunks: list[str] = []
    current = ""
    for section in sections:
        candidate = (current + ("\n\n" if current else "") + section).strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(section) <= max_chars:
            current = section
            continue
        for part in _split_oversize(section, max_chars=max_chars):
            if not current:
                current = part
            elif len(current) + 2 + len(part) <= max_chars:
                current += "\n\n" + part
            else:
                chunks.append(current)
                current = part
    if current:
        chunks.append(current)
    return chunks


def _split_on_section_boundary(text: str) -> list[str]:
    return [part.strip() for part in _SECTION_BOUNDARY.split(text) if part.strip()]


def _split_oversize(section: str, *, max_chars: int) -> list[str]:
    if len(section) <= max_chars:
        return [section]
    output: list[str] = []
    current = ""
    for paragraph in section.split("\n\n"):
        candidate = current + ("\n\n" if current else "") + paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            output.append(current)
            current = ""
        for part in _split_by_line(paragraph, max_chars=max_chars):
            candidate = current + ("\n" if current else "") + part
            if len(candidate) <= max_chars:
                current = candidate
            else:
                output.append(current)
                current = part
    if current:
        output.append(current)
    return output


def _split_by_line(paragraph: str, *, max_chars: int) -> list[str]:
    output: list[str] = []
    current = ""
    for line in paragraph.split("\n"):
        if len(line) > max_chars:
            if current:
                output.append(current)
                current = ""
            output.extend(line[index:index + max_chars]
                          for index in range(0, len(line), max_chars))
            continue
        candidate = current + ("\n" if current else "") + line
        if len(candidate) <= max_chars:
            current = candidate
        else:
            output.append(current)
            current = line
    if current:
        output.append(current)
    return output
