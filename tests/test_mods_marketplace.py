"""tests/test_mods_marketplace.py — the repo-root marketplace that serves mods/ to the fleet.

Every machine installs mc-lane from `pi-dev-ops-mods` with auto-update on. If an
entry pointed at a missing folder, or a mod pinned a `version`, the fleet would
fail to install or silently stop receiving updates; these checks fail first.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKET = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))


def test_marketplace_has_a_name_owner_and_at_least_one_plugin():
    assert MARKET["name"] == "pi-dev-ops-mods"
    assert MARKET["owner"]["name"]
    assert len(MARKET["plugins"]) >= 1


def test_every_entry_points_at_a_mod_folder_with_a_matching_manifest():
    for entry in MARKET["plugins"]:
        src = entry["source"]
        assert isinstance(src, str) and src.startswith("./mods/"), entry
        manifest = ROOT / src / ".claude-plugin" / "plugin.json"
        assert manifest.is_file(), f"{entry['name']}: {manifest} is missing"
        assert json.loads(manifest.read_text(encoding="utf-8"))["name"] == entry["name"]


def test_no_mod_pins_a_version_so_merged_changes_reach_the_fleet():
    """A pinned version holds every machine on its cached copy until someone bumps it."""
    for entry in MARKET["plugins"]:
        assert "version" not in entry, entry["name"]
        manifest = ROOT / entry["source"] / ".claude-plugin" / "plugin.json"
        assert "version" not in json.loads(manifest.read_text(encoding="utf-8")), entry["name"]


def test_every_mod_folder_is_listed():
    listed = {e["source"] for e in MARKET["plugins"]}
    mods = {f"./mods/{p.parent.parent.name}" for p in (ROOT / "mods").glob("*/.claude-plugin/plugin.json")}
    assert mods == listed
