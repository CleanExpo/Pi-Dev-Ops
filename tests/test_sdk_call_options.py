"""RA-7546 — planner SDK calls must not inherit generator tools."""
from app.server.sdk_call_options import (
    is_text_only_phase,
    role_of,
    sdk_query_kwargs,
    usage_output_tokens,
)


def test_planner_role_is_text_only():
    assert role_of("planner") == "planner"
    assert is_text_only_phase("planner") is True
    assert is_text_only_phase("planner.retry") is True
    assert is_text_only_phase("generate") is False
    assert is_text_only_phase("") is False


def test_planner_kwargs_pin_no_tools_and_one_turn():
    opts = sdk_query_kwargs(
        workspace="/tmp/ws",
        model="sonnet",
        thinking_cfg=None,
        effort=None,
        prompt_cache=False,
        tool_gate_on=False,
        can_use_tool=None,
        phase="planner",
    )
    assert opts["allowed_tools"] == []
    assert opts["max_turns"] == 1
    assert opts["setting_sources"] == []
    assert opts["permission_mode"] == "bypassPermissions"


def test_generator_kwargs_keep_full_tools():
    opts = sdk_query_kwargs(
        workspace="/tmp/ws",
        model="sonnet",
        thinking_cfg=None,
        effort=None,
        prompt_cache=True,
        tool_gate_on=False,
        can_use_tool=None,
        phase="generate",
    )
    assert "allowed_tools" not in opts
    assert "max_turns" not in opts
    assert opts["betas"] == ["prompt-caching-2024-07-31"]
    assert opts["permission_mode"] == "bypassPermissions"


def test_usage_output_tokens_reads_dict_and_object():
    assert usage_output_tokens(None) is None
    assert usage_output_tokens({"output_tokens": 12}) == 12

    class _Usage:
        output_tokens = 9

    assert usage_output_tokens(_Usage()) == 9
