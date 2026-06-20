from app.server.agents import board_meeting as bm


def test_prior_research_fresh_when_recent():
    prior = {"findings": [{"sources": [{"url": "u", "fetched": "2999-01-01"}]}]}
    assert bm._prior_research_is_stale(prior, ttl_days=30) is False


def test_prior_research_stale_when_old():
    prior = {"findings": [{"sources": [{"url": "u", "fetched": "2000-01-01"}]}]}
    assert bm._prior_research_is_stale(prior, ttl_days=30) is True


def test_prior_research_stale_when_no_dates():
    prior = {"findings": [{"sources": [{"url": "u"}]}]}
    assert bm._prior_research_is_stale(prior, ttl_days=30) is True
