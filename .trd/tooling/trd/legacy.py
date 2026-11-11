"""TRD legacy audit: fingerprint existing documents and queue unverified passages."""
from __future__ import annotations
import hashlib
from pathlib import Path
from .base import IGNORE_DIRS, LEGACY_EXTENSIONS, now_utc, safe_path, sha256_file

TEXT_EXTENSIONS = {'.md', '.txt', '.rst', '.csv', '.html', '.htm', '.json'}


def inventory(root):
    root = Path(root).resolve()
    files = []
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or not p.is_file() or p.suffix.lower() not in LEGACY_EXTENSIONS:
            continue
        rel = p.relative_to(root)
        if any(part in IGNORE_DIRS for part in rel.parts):
            continue
        files.append({'path': str(rel).replace('\\', '/'), 'sha256': sha256_file(p), 'bytes': p.stat().st_size, 'status': 'UNREVIEWED', 'action': 'Extract material claims and register evidence for retrospective verification'})
    return {'schema': 'trd-legacy-inventory/1', 'root': str(root), 'generated_at': now_utc(), 'files': files, 'note': 'A file fingerprint is not a claim audit. Every prior fact stays UNREVIEWED until converted into a TRD case.'}


def _candidate(paragraph, start_line):
    candidate = '\n'.join(paragraph).strip()
    if candidate and len(candidate) >= 25 and not candidate.startswith('```'):
        return {'line_start': start_line, 'line_end': start_line + len(paragraph) - 1,
                'original_text': candidate, 'status': 'UNVERIFIED',
                'next_step': 'Review and split material facts into atomic claims with evidence source IDs'}
    return None


def _passages(text):
    """Split text on blank lines into candidate paragraphs with line ranges."""
    candidates, paragraph, start_line = [], [], None
    for index, line in enumerate(text.splitlines() + [''], 1):
        if line.strip():
            if start_line is None:
                start_line = index
            paragraph.append(line)
            continue
        found = _candidate(paragraph, start_line)
        if found:
            candidates.append(found)
        paragraph, start_line = [], None
    return candidates


def _read_fingerprinted(target, expected_sha256):
    """Return the file's text only if its bytes still match the inventory fingerprint."""
    data = target.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        return None
    return data.decode('utf-8')


def _backfill_file(root, entry, max_file_bytes):
    item = {'path': entry['path'], 'sha256': entry['sha256'], 'status': 'UNREVIEWED', 'candidates': []}
    try:
        target = safe_path(root, entry['path'])
        size = target.stat().st_size
    except (ValueError, OSError):
        item['next_step'] = 'File missing or unreadable since inventory: re-run inventory before extraction.'
        return item
    if target.suffix.lower() not in TEXT_EXTENSIONS:
        item['next_step'] = 'Extract text with original page/row references in a trusted document parser; review claims individually.'
    elif size > max_file_bytes:
        item['next_step'] = 'Large file requires chunked/streamed extraction and privacy screening.'
    else:
        _fill_candidates(item, target)
    return item


def _fill_candidates(item, target):
    try:
        text = _read_fingerprinted(target, item['sha256'])
    except (UnicodeError, OSError):
        item['next_step'] = 'Cannot read as UTF-8: manual extraction with locators required.'
        return
    if text is None:
        item['next_step'] = 'File changed since inventory (fingerprint mismatch): re-run inventory before extraction.'
        return
    item['candidates'] = _passages(text)
    item['next_step'] = 'Use Claude to propose atomic assertions; JEV challenges them. Register evidence before any PASS.'


def backfill(root, max_file_bytes=2_000_000):
    """Build an unverified passage queue. No semantic truth judgments made."""
    root = Path(root).resolve()
    passages = [_backfill_file(root, entry, max_file_bytes) for entry in inventory(root)['files']]
    return {'schema': 'trd-backfill/1', 'generated_at': now_utc(), 'files': passages,
            'candidate_count': sum(len(i['candidates']) for i in passages),
            'warning': 'Passages are only candidates; not automatically verified facts. All remain UNVERIFIED.'}
