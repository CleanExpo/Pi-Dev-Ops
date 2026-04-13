"""
test_auth.py — Unit tests for authentication, session tokens, and rate limiting.

Covers:
  - SHA-256 legacy hash verification
  - bcrypt hash verification
  - SHA-256 → bcrypt migration trigger
  - Session token creation + verification
  - Expired token rejection
  - Invalid token rejection
  - Rate limiting (sliding window)
"""
import time


def test_sha256_password_correct():
    """Correct password verifies against SHA-256 hash."""
    import hashlib
    from app.server import config, auth
    config.PASSWORD_HASH = hashlib.sha256("correct-password".encode()).hexdigest()
    assert auth.verify_password("correct-password") is True


def test_sha256_password_wrong():
    """Wrong password fails against SHA-256 hash."""
    import hashlib
    from app.server import config, auth
    config.PASSWORD_HASH = hashlib.sha256("correct-password".encode()).hexdigest()
    assert auth.verify_password("wrong-password") is False


def test_sha256_upgrades_to_bcrypt(tmp_path, monkeypatch):
    """Correct SHA-256 login upgrades hash in memory and persists bcrypt to disk."""
    import hashlib
    from app.server import config, auth

    hash_file = tmp_path / ".password-hash"
    monkeypatch.setattr(config, "HASH_FILE", hash_file)
    config.PASSWORD_HASH = hashlib.sha256("test-pass".encode()).hexdigest()

    result = auth.verify_password("test-pass")
    assert result is True
    # Hash in memory is now bcrypt (not 64-char hex)
    assert not auth._is_legacy_hash(config.PASSWORD_HASH)
    # Hash persisted to disk
    assert hash_file.exists()
    persisted = hash_file.read_text().strip()
    assert persisted.startswith("$2b$")


def test_bcrypt_password_correct():
    """Correct password verifies against bcrypt hash."""
    from app.server import config, auth
    config.PASSWORD_HASH = auth.hash_password("bcrypt-test")
    assert auth.verify_password("bcrypt-test") is True


def test_bcrypt_password_wrong():
    """Wrong password fails against bcrypt hash."""
    from app.server import config, auth
    config.PASSWORD_HASH = auth.hash_password("bcrypt-test")
    assert auth.verify_password("not-the-password") is False


def test_session_token_roundtrip():
    """Session token created and verified successfully."""
    from app.server.auth import create_session_token, verify_session_token
    token = create_session_token()
    assert verify_session_token(token) is True


def test_session_token_tampered():
    """Tampered token fails verification."""
    from app.server.auth import create_session_token, verify_session_token
    token = create_session_token()
    parts = token.rsplit(".", 1)
    tampered = parts[0] + "." + "0" * 64
    assert verify_session_token(tampered) is False


def test_session_token_expired(monkeypatch):
    """Expired token is rejected."""
    import json
    import hashlib
    import hmac
    from app.server import config

    now = int(time.time())
    payload = json.dumps({"iat": now - 7200, "exp": now - 3600}, separators=(",", ":"))
    sig = hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    expired_token = f"{payload}.{sig}"

    from app.server.auth import verify_session_token
    assert verify_session_token(expired_token) is False


def test_session_token_invalid_format():
    """Malformed token returns False."""
    from app.server.auth import verify_session_token
    assert verify_session_token("not.a.valid.token.at.all") is False
    assert verify_session_token("") is False
    assert verify_session_token("nodot") is False


def test_rate_limit_allows_within_limit():
    """Requests within rate limit are allowed."""
    from app.server.auth import check_rate_limit, _req_log
    _req_log.clear()
    for _ in range(5):
        assert check_rate_limit("test-ip-allow") is True


def test_rate_limit_blocks_over_limit(monkeypatch):
    """Requests exceeding per-minute limit are blocked."""
    from app.server import config, auth
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 3)
    auth._req_log.clear()
    for _ in range(3):
        auth.check_rate_limit("test-ip-block")
    assert auth.check_rate_limit("test-ip-block") is False


def test_is_legacy_hash():
    """_is_legacy_hash correctly identifies SHA-256 vs bcrypt."""
    from app.server.auth import _is_legacy_hash
    assert _is_legacy_hash("a" * 64) is True
    assert _is_legacy_hash("$2b$12$" + "x" * 53) is False
    assert _is_legacy_hash("short") is False
