"""Tests run without the host's API-key and provider-override variables.

The release gate re-runs this suite from inside a Claude Code session, which can
carry those variables. provider_policy refuses when any is set, so without the
conftest fixture the policy tests passed on GitHub and failed at push time.
"""
import os

from app.server.provider_policy import (
    CLAUDE_ROUTING_ENV,
    CODEX_ROUTING_ENV,
    check_claude_configuration,
)


def test_no_routing_variable_reaches_a_test() -> None:
    present = [key for key in CLAUDE_ROUTING_ENV + CODEX_ROUTING_ENV if os.environ.get(key)]
    assert present == [], f"host routing variables leaked into the test process: {present}"


def test_policy_check_sees_a_clean_process() -> None:
    check_claude_configuration()
