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
# A sign-in or sign-out command, as shell text, split argv (["codex", "login"]) or
# PowerShell (Start-Process, arrays, any parameter order), on one line or across lines.
# Brackets, quotes, commas and @ are blanked first (same length, so line numbers hold),
# which turns every argv and array spelling into plain words. `login status` is a
# read-only check, not a login.
# Limit: this is a text scan of literal command words. A call assembled at run time
# (string joins, variables, splatting) is out of its reach; review is the control for that.
_PUNCT = str.maketrans({c: " " for c in "@()[],\"'"})
_CLI = r"(?:claude|codex|(?:cursor-)?agent)(?:\.exe)?"
_LOG = r"/?log(?:in|out)\b(?!\s+status\b)"
# CLI word, any run of flags (-p, -ArgumentList, -Args, --x), optional `auth`, login/logout.
LOGIN_CALL = re.compile(rf"(?<![\w.-]){_CLI}\s+(?:--?[A-Za-z][\w-]*\s+)*(?:auth\s+)?{_LOG}")
# A quoted "/login" anywhere (a slash command passed to claude in an argv).
SLASH_LOGIN = re.compile(r"""["']/log(?:in|out)["']""")
START_PROCESS = re.compile(r"(?i)\bStart-Process\b")
SP_CLI = re.compile(rf"(?<![\w.-]){_CLI}(?![\w-])")
SP_LOG = re.compile(rf"(?<![\w.-]){_LOG}")
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


def test_w2_every_card_has_the_human_only_banner(text):
    # Every card, machine cards included: the board deep-links to #card-<provider>-<machine>.
    for provider in he.PROVIDERS:
        assert BANNER in _section(text, f"card-{provider}"), provider
        for machine in he.MACHINES:
            assert BANNER in _section(text, f"card-{provider}-{machine}"), (provider, machine)


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


def _statement_end(source: str, i: int) -> int:
    """End of the PowerShell statement starting at i: a newline or ; outside brackets,
    where a backtick before the newline continues the line."""
    depth = 0
    while i < len(source):
        c = source[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth = max(0, depth - 1)
        elif c == "`" and source[i + 1: i + 2] in ("\n", "\r"):
            i += 2
            continue
        elif depth == 0 and c in ";\n":
            break
        i += 1
    return i


def _login_hits(source: str) -> list[int]:
    """Line numbers where a sign-in call starts. Whole-text search over normalised text,
    so argv split across lines and PowerShell parameters in any order still match."""
    norm = source.translate(_PUNCT)
    starts = {m.start() for m in LOGIN_CALL.finditer(norm)}
    starts |= {m.start() for m in SLASH_LOGIN.finditer(source)}
    for m in START_PROCESS.finditer(source):
        stmt = norm[m.end(): _statement_end(source, m.end())]
        if SP_CLI.search(stmt) and SP_LOG.search(stmt):
            starts.add(m.start())
    return sorted({source.count("\n", 0, s) + 1 for s in starts})


def _tracked_code_files() -> list[Path]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.split("\0")
            if p and Path(p).suffix in CODE_SUFFIXES and not p.startswith(SKIP_PREFIXES)]


def test_w5_login_pattern_catches_real_calls():
    for call in ("claude auth login", "codex login --device-auth", "agent login", "cursor-agent logout",
                 'subprocess.run(["codex", "login", "--device-auth"])',
                 "run(['claude', 'auth', 'login'])", 'spawn("cursor-agent", ["login"])',
                 'execFile("agent", [ "logout" ])', 'cmd = ["claude", "-p", "/login"]',
                 "Start-Process codex -ArgumentList login",
                 "Start-Process -FilePath 'claude.exe' -ArgumentList 'auth','login'",
                 'Start-Process "cursor-agent" -ArgumentList "logout"',
                 # Round 4: PowerShell array arguments, aliases and reordered parameters.
                 "Start-Process codex -ArgumentList @('login')",
                 'Start-Process -FilePath claude.exe -ArgumentList @("auth","login")',
                 "Start-Process codex -Args @('logout') -Wait",
                 "Start-Process -ArgumentList login -FilePath codex",
                 "Start-Process -ArgumentList @(\n    'login'\n) -FilePath 'codex.exe'",
                 "Start-Process `\n  -FilePath agent `\n  -ArgumentList 'login'",
                 "& codex.exe @('login')"):
        assert _login_hits(call), call
    for safe in ("codex login status", '["codex", "login", "status"]',
                 "Start-Process codex -ArgumentList 'login','status'",
                 "Start-Process codex -ArgumentList @('login','status')",
                 "Start-Process -ArgumentList @('login', 'status') -FilePath codex",
                 "Start-Process codex -ArgumentList exec\nWrite-Host 'login done'",
                 'r"login expired\\b.*please run /login"'):
        assert not _login_hits(safe), safe


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
