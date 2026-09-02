"""RA-7371 — credential provenance must not be misreported in either direction.

`scripts/sync_slack_bridge_secrets.py` prints one line per secret telling an
operator where it came from. That line was wrong both ways, because the
container overwrote the resolver:

    sources[key] = source if key in raw else "process-env"

`resolve_secret()` answers HOW a value resolved (plaintext vs 1Password);
`key in raw` answers WHETHER the Hermes file mentioned the key. Collapsing two
independent axes into one string produced:

  * an `op://` reference in the process environment, fetched from 1Password,
    reported as loose "process-env" — understating the control in place;
  * a key present-but-EMPTY in the file, whose value therefore came from the
    process environment, reported as "hermes-env" — overstating it, and sending
    an operator to the wrong file to rotate it.

No secret is exposed either way: `sources` is consumed only by
`_report_sources`, which prints "(value not shown)". The harm is a misleading
audit line, which is exactly the kind of claim this repo treats as load-bearing.

This is the FIRST test for this script — it had none, and no CI job or caller
exercises it, so nothing would have caught either direction.

`op` is not installed in CI, so the 1Password path is driven by stubbing
`shutil.which` and `subprocess.run` on the module. That is the boundary the
script itself defines, not a reimplementation of it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sync_slack_bridge_secrets.py"


def load():
    """Load the script by path — `scripts/` is not an importable package."""
    spec = importlib.util.spec_from_file_location("sync_slack_bridge_secrets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["sync_slack_bridge_secrets"] = module
    spec.loader.exec_module(module)
    return module


mod = load()

OP_REF = "op://Private/slack/token"
REAL = "xoxb-REAL-SECRET-FROM-1PASSWORD"


@pytest.fixture
def op_available(monkeypatch):
    """Simulate a host where `op` exists and resolves — CI has no `op`."""
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/local/bin/op")

    class _Proc:
        returncode = 0
        stdout = REAL + "\n"
        stderr = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Proc())


def env_file(tmp_path, body: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def only(sources: dict) -> set:
    """The distinct provenance strings reported, so assertions stay readable."""
    return set(sources.values())


# --------------------------------------------------------------------------
# direction 1 — 1Password understated as loose process env
# --------------------------------------------------------------------------

def test_an_op_ref_in_the_process_env_is_not_reported_as_plain_process_env(
    tmp_path, monkeypatch, op_available
):
    """THE TICKET'S CASE. No Hermes file; both secrets are `op://` refs in env.

    The value genuinely comes from 1Password — `op read` supplied it. Reporting
    that as bare "process-env" tells an operator the credential is sitting
    loose in the environment when it is not.
    """
    for key in mod.SECRET_KEYS:
        monkeypatch.setenv(key, OP_REF)
    missing = tmp_path / "does-not-exist.env"

    values, sources = mod.collect_existing_secrets(missing)

    assert set(values.values()) == {REAL}, "op read did not supply the value"
    assert only(sources) == {"1password (ref from process-env)"}
    assert "process-env" not in only(sources), "the resolver's answer was discarded again"


def test_an_op_ref_in_the_hermes_file_reports_the_file_as_its_origin(
    tmp_path, monkeypatch, op_available
):
    """GREEN CONTROL. Same value, same resolver — only the origin differs.

    Without this the test above would pass equally well against code that
    hardcoded a single string, which is the failure it exists to catch.
    """
    for key in mod.SECRET_KEYS:
        monkeypatch.delenv(key, raising=False)
    path = env_file(tmp_path, "".join(f"{k}={OP_REF}\n" for k in mod.SECRET_KEYS))

    _, sources = mod.collect_existing_secrets(path)

    assert only(sources) == {"1password (ref from hermes-env)"}


# --------------------------------------------------------------------------
# direction 2 — process env overstated as the Hermes file
# --------------------------------------------------------------------------

def test_a_key_present_but_empty_in_the_file_is_not_credited_to_the_file(
    tmp_path, monkeypatch
):
    """The converse misreport, and the reason for `raw.get` over `key in raw`.

    `SLACK_BOT_TOKEN=` parses to an empty string, so the value falls through to
    the process environment — but `key in raw` was still True, so the old code
    reported the Hermes file as the origin. An operator rotating that
    credential would edit a file that does not contain it.
    """
    for key in mod.SECRET_KEYS:
        monkeypatch.setenv(key, "xoxb-PLAINTEXT-FROM-PROCESS-ENV")
    path = env_file(tmp_path, "".join(f"{k}=\n" for k in mod.SECRET_KEYS))

    values, sources = mod.collect_existing_secrets(path)

    assert set(values.values()) == {"xoxb-PLAINTEXT-FROM-PROCESS-ENV"}
    assert only(sources) == {"process-env"}, "an empty file entry claimed the credential"


def test_a_populated_file_entry_is_still_credited_to_the_file(tmp_path, monkeypatch):
    """GREEN CONTROL for the test above — `hermes-env` must remain reachable."""
    for key in mod.SECRET_KEYS:
        monkeypatch.setenv(key, "xoxb-SHOULD-NOT-WIN")
    path = env_file(tmp_path, "".join(f"{k}=xoxb-FROM-FILE\n" for k in mod.SECRET_KEYS))

    values, sources = mod.collect_existing_secrets(path)

    assert set(values.values()) == {"xoxb-FROM-FILE"}, "file must take precedence"
    assert only(sources) == {"hermes-env"}


# --------------------------------------------------------------------------
# the resolver's own contract
# --------------------------------------------------------------------------

def test_resolve_secret_reports_resolution_not_origin():
    """`plaintext` replaced `hermes-env`, which named an origin this function
    cannot know — it never sees where the candidate came from."""
    assert mod.resolve_secret("xoxb-abc", key="SLACK_BOT_TOKEN") == ("xoxb-abc", "plaintext")


def test_resolve_secret_refuses_an_op_ref_with_no_op_cli(monkeypatch):
    """Fail closed: never silently treat an unresolved `op://` string as the
    secret itself, which would push the literal reference to Railway."""
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="op` CLI is unavailable"):
        mod.resolve_secret(OP_REF, key="SLACK_BOT_TOKEN")


def test_a_missing_secret_raises_rather_than_reporting_a_source(tmp_path, monkeypatch):
    """Nothing anywhere — the script must stop, not invent provenance."""
    for key in mod.SECRET_KEYS:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="was not found"):
        mod.collect_existing_secrets(tmp_path / "absent.env")
