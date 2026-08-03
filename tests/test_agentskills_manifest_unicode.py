"""Non-BMP serializer regression (RA-7057 review): _yaml_scalar must emit
YAML that strict parsers accept and that round-trips to the original string,
never \\ud83d-style surrogate-pair escapes (invalid for Ruby Psych; PyYAML
loads them as two surrogate code points)."""

import yaml

from swarm.agentskills_manifest import _yaml_scalar


def test_yaml_scalar_non_bmp_no_surrogate_escapes():
    # Force the quoted branch with a colon so json.dumps path is exercised.
    original = "thumbs: \U0001F44D up"
    emitted = _yaml_scalar(original)
    assert "\\ud83d" not in emitted.lower()
    assert yaml.safe_load(emitted) == original


def test_yaml_scalar_plain_non_bmp_round_trips():
    original = "\U0001F44D"
    emitted = _yaml_scalar(original)
    assert yaml.safe_load(emitted) == original
