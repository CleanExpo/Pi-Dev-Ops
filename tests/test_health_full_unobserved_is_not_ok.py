"""A health check that could not run must not report the component healthy.

Estate audit rows H01-H04. The operating doctrine in CLAUDE.md is explicit:

    "A read that failed must never render as a read that succeeded and found
    nothing; a check that could not run must never report as a check that
    passed."

`health_full.py` broke that in ten places by returning `ok: True` alongside
`observed: False`, and in three `except` handlers that answered `ok: True`
after the probe had raised. Anything reading `components.<name>.ok` — a
dashboard, a pinger, Mission Control — saw green for a component nobody looked
at.

Two source guards and two behavioural tests. The source guards exist because
the defect is a shape repeated across seven functions, and a behavioural test
per site would need seven different fakes; the behavioural tests exist because
a source guard alone proves only that the text changed.

Every one of these four was watched FAILING against the unfixed file before the
fix was written.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path

import pytest

from app.server.routes import health_full


HEALTH_SRC = Path(health_full.__file__)


def _run(coro):
    return asyncio.run(coro)


def _check_functions(tree: ast.AST) -> list[ast.AsyncFunctionDef]:
    return [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
        and n.name.startswith("_check_")
    ]


def _const_dict(node: ast.AST) -> dict | None:
    """The literal key/value pairs of a returned dict, or None if not literal.

    Mirrors how the estate-audit probe reads this file. A return the reader
    cannot evaluate is not a return it judged clean, so callers treat None as
    "unjudgeable" rather than "fine".
    """
    if not isinstance(node, ast.Dict):
        return None
    out = {}
    for k, v in zip(node.keys, node.values):
        if not isinstance(k, ast.Constant):
            return None
        try:
            out[k.value] = ast.literal_eval(v)
        except (ValueError, TypeError, SyntaxError):
            out[k.value] = "<computed>"
    return out


def test_source_is_parseable_and_has_the_checks():
    """Positive control. Without this, an empty result below proves nothing."""
    tree = ast.parse(HEALTH_SRC.read_text(encoding="utf-8"))
    funcs = _check_functions(tree)
    assert len(funcs) >= 7, "expected the seven component checks, found %d" % len(funcs)
    observed_keys = 0
    for fn in funcs:
        for node in ast.walk(fn):
            if isinstance(node, ast.Return):
                pairs = _const_dict(node.value)
                if pairs and "observed" in pairs:
                    observed_keys += 1
    assert observed_keys > 0, (
        "no returned dict carries an 'observed' key, so this file cannot be "
        "judged on the ok/observed invariant at all"
    )


def test_no_check_reports_ok_while_unobserved():
    """H01, H02, H03 - beside observed False, ok must be LITERALLY False.

    Fails closed on a computed `ok`, and that is the whole point of the rule.
    An earlier version asked only whether `ok` was the literal True, so a
    non-literal True slipped straight past it:

        _ok = True
        return {"ok": _ok, "observed": False, "status": "not_observed", ...}

    `_const_dict` records that as "<computed>", the offender test skipped it,
    and the file that claims to lock this invariant stayed green with the lie
    present. Found by the independent reviewer (cursor, P1) on head 767e445d
    and confirmed by planting exactly that mutant: 6 passed with the defect in.

    There is no legitimate reason to compute `ok` on a path that already knows
    it never observed anything, so refusing to judge is refusing to pass.
    """
    tree = ast.parse(HEALTH_SRC.read_text(encoding="utf-8"))
    offenders = []
    for fn in _check_functions(tree):
        for node in ast.walk(fn):
            if not isinstance(node, ast.Return):
                continue
            pairs = _const_dict(node.value)
            if not pairs or pairs.get("observed") is not False:
                continue
            if pairs.get("ok") is not False:
                offenders.append(
                    "%s:%d ok=%r (%s)" % (fn.name, node.lineno, pairs.get("ok"),
                                          pairs.get("note") or pairs.get("status") or "?")
                )
    assert not offenders, (
        "a check that could not run must report ok=False, not %s, at: %s"
        % ("a computed value" if any("<computed>" in o for o in offenders) else "ok=True",
           ", ".join(offenders))
    )


def test_no_except_handler_reports_ok():
    """H04 — a component whose probe raised is not a healthy component."""
    tree = ast.parse(HEALTH_SRC.read_text(encoding="utf-8"))
    offenders = []
    denied = 0
    for fn in _check_functions(tree):
        for handler in [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]:
            for node in ast.walk(handler):
                if not isinstance(node, ast.Return):
                    continue
                pairs = _const_dict(node.value)
                if not pairs:
                    continue
                if pairs.get("ok") is True:
                    offenders.append("%s:%d" % (fn.name, node.lineno))
                elif pairs.get("ok") is False:
                    denied += 1
    assert denied > 0, (
        "no except handler was seen denying ok, so finding no offender here "
        "would say nothing about the file"
    )
    assert not offenders, (
        "an except handler answers healthy after the probe raised at: %s"
        % ", ".join(offenders)
    )


def test_hermes_gateway_without_heartbeat_is_not_ok(tmp_path, monkeypatch):
    """Behavioural. The absent-file path is the one that lied most often."""
    monkeypatch.setattr(health_full, "_HARNESS", tmp_path)
    result = _run(health_full._check_hermes_gateway())
    assert result["observed"] is False, "sanity: this path must be the unobserved one"
    assert result["ok"] is False, (
        "no heartbeat file means the check could not run; it must not report ok"
    )


def test_endpoint_stays_200_when_the_only_problem_is_unobserved(monkeypatch):
    """The reason the lie was there in the first place, kept working honestly.

    Hermes runs on the Mac mini, so its heartbeat is legitimately absent on the
    Railway host. That must not 503 the public endpoint. The fix is to judge the
    HTTP status on components that were actually observed, not to let an
    unobserved component claim ok.
    """
    async def observed_ok():
        return {"ok": True, "observed": True, "status": "live"}

    async def unobserved():
        return {"ok": False, "observed": False, "status": "not_observed",
                "note": "no_heartbeat_file_on_this_host"}

    checks = {name: observed_ok for name in health_full._CHECKS}
    checks["hermes_gateway"] = unobserved
    monkeypatch.setattr(health_full, "_CHECKS", checks)

    response = _run(health_full.health_full())
    body = json.loads(response.body)

    assert response.status_code == 200, (
        "an unobserved component must not 503 the endpoint; got %d" % response.status_code
    )
    assert body["degraded_components"] == ["hermes_gateway"]
    assert body["red_components"] == []
    assert body["fully_observed"] is False


def test_endpoint_still_503s_when_an_observed_component_is_red(monkeypatch):
    """The other side of the pair: honesty must not cost us the real alarm."""
    async def observed_ok():
        return {"ok": True, "observed": True, "status": "live"}

    async def observed_red():
        return {"ok": False, "observed": True, "status": "red"}

    checks = {name: observed_ok for name in health_full._CHECKS}
    checks["supabase"] = observed_red
    monkeypatch.setattr(health_full, "_CHECKS", checks)

    response = _run(health_full.health_full())
    body = json.loads(response.body)

    assert response.status_code == 503
    assert body["red_components"] == ["supabase"]
