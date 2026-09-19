"""Reject a deployment lock that no longer satisfies the declared dependencies."""
from pathlib import Path
import re

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_lock_satisfies_each_declared_dependency():
    locked = {}
    text = (ROOT / "app/requirements.lock").read_text()
    for line in text.splitlines():
        if match := re.match(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", line):
            locked[canonicalize_name(match[1])] = match[2]
    assert locked, "Runtime lock must not be empty"
    for line in (ROOT / "app/requirements.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        declared = Requirement(line)
        name = canonicalize_name(declared.name)
        assert name in locked, f"Missing runtime dependency: {name}"
        assert locked[name] in declared.specifier, f"Stale runtime pin for {name}"


def test_every_locked_requirement_has_distribution_hashes():
    entries = re.split(r"\n(?=[A-Za-z0-9])", (ROOT / "app/requirements.lock").read_text())
    for entry in entries:
        if not entry.strip():
            continue
        assert re.match(r"^[A-Za-z0-9_.-]+==", entry), "Only exact registry pins may enter the runtime lock"
        assert re.search(r"--hash=sha256:[0-9a-f]{64}(?:\s|$)", entry), entry.splitlines()[0]
