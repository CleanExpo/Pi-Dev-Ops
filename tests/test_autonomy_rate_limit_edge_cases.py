"""Linear quota envelope and cooldown edge cases."""

import random
import time

from app.server import autonomy, autonomy_linear_rate
from app.server.routes import mission_control


def test_1000_varied_linear_error_envelopes_have_exact_quota_classification():
    rng = random.Random(20260929)
    for index in range(1000):
        errors = [{"extensions": {"code": rng.choice(["QUOTA_EXCEEDED", "UNKNOWN", "INTERNAL"])}}
                  for _ in range(rng.randrange(5))]
        rate_limited = index % 3 == 0
        if rate_limited:
            errors.insert(rng.randrange(len(errors) + 1), {
                "message": f"variant-{index}@example.test",
                "extensions": {"code": "RATELIMITED", "statusCode": 429},
            })
        assert autonomy._has_linear_rate_limit_error({"errors": errors}) is rate_limited
    assert not autonomy._has_linear_rate_limit_error({"errors": "malformed"})


def test_expired_cooldown_permits_refresh(monkeypatch):
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    now = time.monotonic()
    monkeypatch.setattr(autonomy_linear_rate, "_rate_limited_until", now - 1)
    calls = []
    monkeypatch.setattr(mission_control, "_queue_snapshot", lambda: (
        calls.append("queue") or {"next_issue_id": "A-1"}
    ))
    assert mission_control._cached_queue_snapshot()["next_issue_id"] == "A-1"
    assert calls == ["queue"]
