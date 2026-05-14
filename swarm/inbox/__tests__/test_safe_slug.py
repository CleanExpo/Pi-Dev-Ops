import pytest
from swarm.inbox.safe_slug import validate_slug, SafeSlugError


def test_valid_slugs():
    for s in ['ccw', 'duncan', 'unite-group', 'dr-nrpg', 'restoreassist']:
        assert validate_slug(s) == s


@pytest.mark.parametrize("bad", [
    "../etc/passwd", "/absolute/path", "with space",
    "WithUpperCase", "../../escape", "-leading-dash",
    "trailing-dash-", "a" * 100,  # too long
])
def test_invalid_slugs_raise(bad):
    with pytest.raises(SafeSlugError):
        validate_slug(bad)
