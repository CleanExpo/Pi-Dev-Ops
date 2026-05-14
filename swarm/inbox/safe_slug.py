"""Path-traversal-safe slug validation. Per Magnus P19 (browser-harness _ipc.py:22)."""
import re

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class SafeSlugError(ValueError):
    """Raised when a slug fails path-traversal-safe validation."""


def validate_slug(slug: str) -> str:
    """Validate slug against path-traversal patterns. Returns the slug or raises."""
    if not isinstance(slug, str):
        raise SafeSlugError(f"slug must be str, got {type(slug).__name__}")
    if not _SLUG_RE.match(slug):
        raise SafeSlugError(f"invalid slug: {slug!r}")
    return slug
