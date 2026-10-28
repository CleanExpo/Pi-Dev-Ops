"""Census: every module that can reach TypeSafe records the call in the machine spend ledger (spec C3).

A module reaches TypeSafe when its text names typesafe.ai, or when it imports the shadow script's `evaluate`
(which posts there without naming it). Each such module must route through one of the recorders. Gemini
modules use a different vendor and are out of scope (spec section 5, Out)."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = re.compile(r"typesafe\.ai", re.IGNORECASE)
SHADOW_EVALUATE = re.compile(r"from scripts\.mission_control_jev_shadow import[^\n]*\bevaluate\b")
RECORDERS = ("spend.reserve(", "reserve_call(", "client.send(")


def reaches_typesafe(text: str) -> bool:
    return bool(ENDPOINT.search(text) or SHADOW_EVALUATE.search(text))


def unrecorded(paths: list[Path]) -> list[str]:
    out = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if reaches_typesafe(text) and not any(r in text for r in RECORDERS):
            out.append(str(path))
    return out


def tracked_modules() -> list[Path]:
    names = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / n for n in names.split() if not n.startswith("tests/")]


def test_every_module_that_reaches_typesafe_records_its_spend():
    modules = tracked_modules()
    reaching = [p for p in modules if reaches_typesafe(p.read_text(encoding="utf-8", errors="replace"))]
    assert len(reaching) >= 5, reaching  # the scan sees the known endpoint files; an empty census proves nothing
    assert unrecorded(modules) == []


def test_census_flags_a_planted_module_that_names_the_endpoint(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text('URL = "https://api.TypeSafe.ai/v1/systemone"\n')
    assert unrecorded([planted]) == [str(planted)]


def test_census_flags_a_planted_module_that_imports_the_shadow_evaluate(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text("from scripts.mission_control_jev_shadow import MODEL, evaluate\n")
    assert unrecorded([planted]) == [str(planted)]


def test_census_accepts_a_module_that_records(tmp_path):
    ok = tmp_path / "ok.py"
    ok.write_text('URL = "https://api.typesafe.ai/v1/systemone"\nrow = spend.reserve("x", 0.1)\n')
    assert unrecorded([ok]) == []
