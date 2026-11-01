"""Independent page scope, source-bound Chromium screenshots and browser health."""
from pathlib import Path

from sda_gate_core import REQUIRED_VIEWPORTS, VIEWPORTS, strict_json
from sda_gate_png import png_dimensions


def _independent_scope(root, scope_record, errors):
    if not scope_record:
        errors.append("independent scope record required (--scope-record)")
        return None
    scoped = Path(scope_record).resolve()
    if scoped.is_relative_to(root) or not scoped.is_file():
        errors.append("scope record must exist outside candidate directory")
        return None
    try:
        scope = strict_json(scoped.read_text(encoding="utf-8"))
        if (not isinstance(scope, dict) or
                not isinstance(scope.get("expected_pages"), list) or
                not scope["expected_pages"] or
                any(not isinstance(v, str) or not v for v in scope["expected_pages"]) or
                len(set(scope["expected_pages"])) != len(scope["expected_pages"]) or
                not scope.get("scope_owner") or not scope.get("scoped_at")):
            raise ValueError("scope pages, owner and timestamp required")
    except (OSError, ValueError) as exc:
        errors.append("independent scope invalid: " + str(exc))
        return None
    return scope


def _audits(doc, asset, errors):
    audit = doc.get("audit") or {}
    if not isinstance(audit, dict):
        errors.append("Playwright audit manifest must be an object")
        audit = {}
    audit_bytes = asset(audit.get("file"), audit.get("sha256"), "Playwright audit")
    audits = []
    if audit_bytes:
        try:
            audits = strict_json(audit_bytes[1].decode("utf-8"))
        except (OSError, ValueError) as exc:
            errors.append("Playwright audit cannot be parsed: " + str(exc))
    if not isinstance(audits, list) or not audits:
        errors.append("Playwright audit has no pages")
        audits = []
    return audits


def _page_contract(doc, scope, errors):
    pages = doc.get("expected_pages") or []
    if (not isinstance(pages, list) or not pages or
            any(not isinstance(p, str) or not p for p in pages) or
            len(pages) != len(set(pages))):
        errors.append("expected_pages must be distinct nonempty names")
        pages = []
    if scope is not None and sorted(pages) != sorted(scope["expected_pages"]):
        errors.append("candidate expected_pages differs from independent scope record")
    shot_map = doc.get("screenshots") or {}
    if not isinstance(shot_map, dict):
        errors.append("screenshots must be a map")
        shot_map = {}
    return pages, shot_map


def _check_measurements(rec, label, expected_width, errors):
    if type(rec.get("viewport")) is not int or rec["viewport"] != expected_width:
        errors.append(label + ": viewport width missing/wrong")
    if type(rec.get("status")) is not int or rec["status"] != 200:
        errors.append(label + ": HTTP not 200")
    if type(rec.get("brokenImages")) is not int or rec["brokenImages"] != 0:
        errors.append(label + ": broken-image measurement missing or nonzero")
    for field in ("overflowing", "errors"):
        value = rec.get(field)
        if not isinstance(value, list):
            errors.append(label + ": " + field + " measurement missing/invalid")
        elif value:
            errors.append(label + ": " + field + " nonempty: " + str(value)[:160])


def _check_screenshot(rec, label, width, height, root, shot_map, asset, errors, used_files, used_inodes):
    filename = rec.get("shot")
    if not isinstance(filename, str):
        errors.append(label + ": screenshot filename missing")
        filename = ""
    canonical = (root / filename).resolve() if filename else None
    if canonical in used_files:
        errors.append(label + ": screenshot path reused through alias across pages/viewports")
    used_files.add(canonical)
    screenshot = asset(filename, shot_map.get(filename), label + " screenshot")
    if not screenshot:
        return
    if screenshot[2] in used_inodes:
        errors.append(label + ": screenshot physical file reused through hard link across pages/viewports")
    used_inodes.add(screenshot[2])
    try:
        w, h = png_dimensions(screenshot[1])
        if w != width or h < height:
            raise ValueError("dimensions " + str((w, h)) + " do not match " + str((width, height)))
    except ValueError as exc:
        errors.append(label + ": screenshot decode/dimensions fail: " + str(exc))


def _check_row(rec, pages, root, shot_map, asset, errors, seen_pairs, seen_files, seen_inodes):
    if not isinstance(rec, dict):
        errors.append("audit row must be an object")
        return
    name, viewport = rec.get("name"), rec.get("label")
    label = str(name) + "/" + str(viewport)
    if not isinstance(name, str) or not isinstance(viewport, str) or name not in pages or viewport not in VIEWPORTS:
        errors.append(label + ": unexpected page or viewport")
        return
    pair = (name, viewport)
    if pair in seen_pairs:
        errors.append(label + ": duplicate audit row")
    seen_pairs.add(pair)
    width, height = VIEWPORTS[viewport]
    _check_measurements(rec, label, width, errors)
    _check_screenshot(rec, label, width, height, root, shot_map, asset, errors, seen_files, seen_inodes)


def validate_browser(doc, root, scope_record, asset, errors):
    scope = _independent_scope(root, scope_record, errors)
    audits = _audits(doc, asset, errors)
    pages, shot_map = _page_contract(doc, scope, errors)
    seen_pairs, seen_files, seen_inodes = set(), set(), set()
    for rec in audits:
        _check_row(rec, pages, root, shot_map, asset, errors, seen_pairs, seen_files, seen_inodes)
    for name in pages:
        for viewport in REQUIRED_VIEWPORTS:
            if (name, viewport) not in seen_pairs:
                errors.append(name + ": missing viewports " + viewport)
