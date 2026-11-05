"""Guards the human sign-in runbook (RA-8192, AR-06).

Each test names the why (W1-W5 in the PR body) it traces to. The runbook is for a
person; these checks keep it complete for every provider and machine the HEADROOM
log knows, and keep sign-in commands out of anything an agent runs.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNBOOK = ROOT / "docs" / "runbooks" / "sign-in.md"
sys.path.insert(0, str(ROOT / "scripts"))
import headroom_events as he  # noqa: E402

BANNER = "HUMAN ONLY"
STATUS_CMD = {"claude": "claude auth status", "codex": "codex login status", "cursor": "agent status"}
LOGIN_CMD = {"claude": "claude auth login", "codex": "codex login", "cursor": "agent login"}
# Flags that turn a subscription sign-in into an API-key, token or metered login.
BANNED_IN_SHELL = re.compile(r"--with-api-key|--with-access-token|--console\b|_API_KEY\b|ACCESS_TOKEN\b")
# A sign-in or sign-out command, as shell text or as split argv (["codex", "login"]),
# on one line or across lines. `codex login status` is a read-only check, not a login.
# Limit: this is a text scan of literal command words. A call assembled at run time
# (string joins, variables) is out of its reach; review is the control for that.
_Q = r"""["']"""
_SEP = r"""["']\s*,\s*\[?\s*["']"""
LOGIN_CALL = re.compile(
    r"\bclaude\s+auth\s+log(?:in|out)\b|\bcodex\s+log(?:in(?!\s+status)|out)\b"
    r"|\b(?:cursor-)?agent\s+log(?:in|out)\b"
    rf"|{_Q}claude{_SEP}auth{_SEP}log(?:in|out){_Q}"
    rf"|{_Q}codex{_SEP}log(?:out{_Q}|in{_Q}(?!\s*,\s*{_Q}status{_Q}))"
    rf"|{_Q}(?:cursor-)?agent{_SEP}log(?:in|out){_Q}"
    rf"|{_Q}/log(?:in|out){_Q}")
# Every tracked code file except tests (which plant calls on purpose) and vendored code.
SKIP_PREFIXES = ("tests/", "vendor/")
CODE_SUFFIXES = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".ps1", ".cmd", ".bat"}


@pytest.fixture(scope="module")
def text() -> str:
    assert RUNBOOK.is_file(), f"missing runbook: {RUNBOOK.relative_to(ROOT)}"
    return RUNBOOK.read_text(encoding="utf-8")


def _anchors(text: str) -> set[str]:
    return set(re.findall(r'<a id="([a-z0-9-]+)"></a>', text))


def _section(text: str, anchor: str) -> str:
    """Text from an anchor up to the next anchor of the same or a shorter kind."""
    start = text.index(f'<a id="{anchor}"></a>')
    nxt = re.search(r'<a id="[a-z0-9-]+"></a>', text[start + 1:])
    return text[start: start + 1 + nxt.start()] if nxt else text[start:]


def _provider_block(text: str, provider: str) -> str:
    """The provider card plus all its per-machine cards."""
    start = text.index(f'<a id="card-{provider}"></a>')
    nxt = re.search(r'<a id="(?!card-' + provider + r'-)[a-z0-9-]+"></a>', text[start + 1:])
    return text[start: start + 1 + nxt.start()] if nxt else text[start:]


def _shell_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:bash|sh|zsh|powershell|pwsh)\n(.*?)```", text, re.S)


def test_w1_one_card_per_provider_and_machine(text):
    anchors = _anchors(text)
    for provider in he.PROVIDERS:
        assert f"card-{provider}" in anchors, provider
        for machine in he.MACHINES:
            assert f"card-{provider}-{machine}" in anchors, (provider, machine)


def test_w2_every_provider_card_has_the_human_only_banner(text):
    for provider in he.PROVIDERS:
        assert BANNER in _section(text, f"card-{provider}"), provider


def test_w3_every_machine_card_has_status_check_and_sign_in(text):
    for provider in he.PROVIDERS:
        for machine in he.MACHINES:
            card = _section(text, f"card-{provider}-{machine}")
            assert STATUS_CMD[provider] in card, (provider, machine, "status")
            assert LOGIN_CMD[provider] in card, (provider, machine, "login")


def test_w3_cards_name_the_account_by_map_label_never_an_email(text):
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), "runbook must not carry an email"
    for provider in he.PROVIDERS:
        assert "ACCOUNT-MAP" in _provider_block(text, provider), provider


def test_w4_every_headroom_event_maps_to_a_real_card(text):
    anchors = _anchors(text)
    table = _section(text, "state-to-card")
    for event in he.EVENTS:
        rows = [ln for ln in table.splitlines() if ln.startswith(f"| `{event}`")]
        assert len(rows) == 1, event
        links = re.findall(r"\(#([a-z0-9-]+)\)", rows[0])
        assert links, event
        for link in links:
            assert link in anchors, (event, link)
    auth_row = next(ln for ln in table.splitlines() if ln.startswith("| `auth_expired`"))
    assert "card-<provider>-<machine>" in auth_row


def test_w4_codex_credits_line_is_a_sign_in_not_billing(text):
    codex = _provider_block(text, "codex")
    assert "Your workspace is out of credits" in codex
    assert "not billing" in codex.lower()
    assert "401 Unauthorized" in codex  # codex.unauthorized, RA-8191
    assert "docs/codex-failover.md" in codex


def test_w5_no_shell_block_uses_a_key_or_token_login(text):
    blocks = _shell_blocks(text)
    assert blocks, "runbook has no shell blocks"
    for block in blocks:
        assert not BANNED_IN_SHELL.search(block), block


def _login_hits(source: str) -> list[int]:
    """Line numbers where a sign-in call starts. Whole-text search, so argv split
    across lines still matches (the separators allow newlines)."""
    return [source.count("\n", 0, m.start()) + 1 for m in LOGIN_CALL.finditer(source)]


def _tracked_code_files() -> list[Path]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.split("\0")
            if p and Path(p).suffix in CODE_SUFFIXES and not p.startswith(SKIP_PREFIXES)]


def test_w5_login_pattern_catches_real_calls():
    for call in ("claude auth login", "codex login --device-auth", "agent login", "cursor-agent logout",
                 'subprocess.run(["codex", "login", "--device-auth"])',
                 "run(['claude', 'auth', 'login'])", 'spawn("cursor-agent", ["login"])',
                 'execFile("agent", [ "logout" ])', 'cmd = ["claude", "-p", "/login"]'):
        assert LOGIN_CALL.search(call), call
    for safe in ("codex login status", '["codex", "login", "status"]',
                 'r"login expired\\b.*please run /login"'):
        assert not LOGIN_CALL.search(safe), safe


def test_w5_scan_catches_a_call_split_across_lines():
    source = 'import subprocess\nsubprocess.run([\n    "codex",\n    "login",\n    "--device-auth",\n])\n'
    assert _login_hits(source) == [3]
    assert _login_hits('subprocess.run([\n    "codex",\n    "login",\n    "status",\n])\n') == []


def test_w5_scan_covers_agent_hooks_and_the_whole_tracked_tree():
    scanned = {p.relative_to(ROOT).as_posix() for p in _tracked_code_files()}
    assert any(p.startswith(".claude/hooks/") for p in scanned), "agent hooks not scanned"
    assert not any(p.startswith("tests/") for p in scanned), "tests hold planted calls on purpose"


def test_w5_no_tracked_code_runs_a_sign_in_command():
    files = _tracked_code_files()
    assert files, "git ls-files found no code to scan"
    hits = []
    for path in files:
        if path == Path(__file__).resolve() or not path.is_file():
            continue
        for n in _login_hits(path.read_text(encoding="utf-8", errors="replace")):
            hits.append(f"{path.relative_to(ROOT)}:{n}")
    assert not hits, hits
