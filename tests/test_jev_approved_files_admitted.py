"""Every approved file passes admission, and the screen that admits them still refuses keys.

On 31/10/2026 the scout skipped client.py as "sensitive content": the source held the literal
fail-closed sentinel, which matched the API-key screen. The sentinel is now built at run time.
These tests keep both halves true: the four approved files are admitted, and real, encoded and
undecodable keys are still refused. Offline; no request is made. Key-shaped values are built
from parts so this file holds no literal that looks like a credential.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from jev_platform import ask, client

REPO = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((REPO / ask.MANIFEST).read_text())
FAKE_KEY = "sk" + "-" + "a1b2c3d4e5f6g7h8"


@pytest.mark.parametrize("rel", sorted(MANIFEST["files"]))
def test_every_approved_file_is_admitted(rel):
    text, digest, refusal = ask.admit(str(REPO), MANIFEST, rel)
    assert refusal is None, f"{rel} refused: {refusal}"
    assert digest == MANIFEST["files"][rel] and text


def test_all_four_approved_files_are_listed():
    assert sorted(MANIFEST["files"]) == sorted(
        f"jev_platform/{n}.py" for n in ("calibration", "client", "engine", "policy"))


@pytest.mark.parametrize("text", [
    FAKE_KEY,
    "log: " + FAKE_KEY + " end",
    "\\x73k-" + "a1b2c3d4e5f6g7h8",        # written-out hex escape for the first letter
    "\\u0073k-" + "a1b2c3d4e5f6g7h8",      # written-out unicode escape
    "\\\\x73k-" + "a1b2c3d4e5f6g7h8",      # escaped twice
])
def test_real_and_encoded_keys_are_still_refused(text):
    assert client.credential(text)
    assert ask.sensitive(text)


def test_undecodable_text_fails_closed():
    deep = "\\" * (2 ** (client._MAX_DEPTH + 2)) + "x"  # halves once per round, never settles in time
    assert client._stages(deep) is None
    assert client.UNSETTLED in client.screened(deep)
    assert client.credential(deep)
    assert ask.sensitive(deep)


def test_the_sentinel_still_matches_the_key_screen():
    assert client._API_KEYS.search(client.UNSETTLED)
    assert any(p.search(client.UNSETTLED) for p in client.CREDENTIALS)


@pytest.mark.parametrize("rel", sorted(MANIFEST["files"]))
def test_a_changed_file_fails_the_approved_hash(tmp_path, rel):
    for r in MANIFEST["files"]:
        (tmp_path / r).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / r, tmp_path / r)
    (tmp_path / rel).write_bytes((REPO / rel).read_bytes() + b"\n# changed\n")
    text, _, refusal = ask.admit(str(tmp_path), MANIFEST, rel)
    assert text is None and refusal == "content differs from approved sha256"
