"""tests/test_mcp_conversation_tools.py — the cross-machine conversation surface.

`mcp/pi-ceo-server.js` has no JS test harness in this repo; the existing
`test_pi_ceo_mcp_staleness.py` guards it by asserting on its source, and this
follows that convention.

What is worth pinning here is not that two tools exist — it is the two
properties that make them safe and useful: the surface is READ-ONLY (a session
can search history, never rewrite it), and an unconfigured machine reports
itself as unconfigured rather than as a machine with no history. Those two
failures look identical to a user and mean opposite things.
"""
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = (REPO_ROOT / "mcp" / "pi-ceo-server.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("tool", ["conversation_search", "conversation_recent"])
def test_tool_is_registered_and_dispatchable(tool: str) -> None:
    assert f'server.registerTool(\n  "{tool}"' in SOURCE, f"{tool} not registered"
    assert f'_readHandlers.set("{tool}"' in SOURCE, f"{tool} missing from the parallel dispatch map"


@pytest.mark.parametrize("tool", ["conversation_search", "conversation_recent"])
def test_tool_is_declared_read_only(tool: str) -> None:
    """Both must be in READ_ONLY_TOOLS: run_parallel may only fan out safe tools."""
    block = SOURCE[SOURCE.index("const READ_ONLY_TOOLS"):SOURCE.index("// Internal dispatch map")]
    assert f'"{tool}"' in block


def test_the_conversation_surface_has_no_write_tool():
    """Digests come from each machine's collector, never from an agent.

    A write tool here would let any session fabricate another machine's history,
    which is worse than having no shared history at all.
    """
    for forbidden in ("conversation_write", "conversation_ingest", "conversation_delete"):
        assert forbidden not in SOURCE, f"{forbidden} would make this surface writable"
    # The ingest endpoint is the collector's, and must not be reachable from here.
    assert "/api/conversations/ingest" not in SOURCE


def test_missing_credential_is_reported_as_unconfigured_not_as_empty():
    """"No key" and "no results" must never render the same.

    Silent-empty is the failure mode this whole milestone exists to remove: a
    machine that cannot reach the store would otherwise look exactly like a
    fleet that has never had a conversation.
    """
    assert "PI_CEO_API_KEY not set" in SOURCE
    assert "cannot reach the shared conversation store" in SOURCE


def test_disabled_server_is_named_distinctly_too():
    assert "CONVERSATION_SYNC_ENABLED unset" in SOURCE


def test_startup_banner_does_not_hardcode_a_tool_count():
    """It claimed 26 while 31 were registered — a number nobody maintained.

    CLAUDE.md rule 2: name the command, never paste the measurement.
    """
    assert "26 tools" not in SOURCE
    assert "tools)" not in SOURCE.split("started (stdio transport")[1][:40]
    assert 'grep -c "^server.registerTool("' in SOURCE, "no re-derivation command recorded"
