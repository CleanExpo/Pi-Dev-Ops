from pathlib import Path


def test_stale_analysis_advice_names_real_regeneration_path():
    source = Path("mcp/pi-ceo-server.js").read_text(encoding="utf-8")

    assert "get_last_analysis` after a full board meeting" not in source
    assert "checked-in analysis snapshot" in source
    assert "scripts/analyze.sh" in source
