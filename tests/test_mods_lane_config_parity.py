"""tests/test_mods_lane_config_parity.py — the two copies of lane_config.ts stay identical.

mission-control and mc-lane are installed as separate plugins, so neither can import
the other's code. Both read the Mission Control link settings the same way (process
environment, then launchd: see the header of lane_config.ts), so each carries its own
copy. Two copies drift; this pins them byte for byte. Edit both or neither.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = [
    ROOT / "mods" / "mission-control" / "hooks" / "lane_config.ts",
    ROOT / "mods" / "mc-lane" / "hooks" / "lane_config.ts",
]


def test_both_copies_exist_and_are_not_empty():
    # Two missing files compare equal, so existence is asserted first.
    for path in COPIES:
        assert path.is_file(), f"missing: {path.relative_to(ROOT)}"
        assert path.stat().st_size > 0, f"empty: {path.relative_to(ROOT)}"


def test_copies_are_byte_identical():
    first, second = (p.read_bytes() for p in COPIES)
    assert first == second, "mods/*/hooks/lane_config.ts differ: copy the edited one over the other"
