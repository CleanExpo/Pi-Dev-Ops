"""Skill router: pin, then free lexical shortlist, then one Jev pick, then load only that body."""
import json
from pathlib import Path

import pytest

from src.tao import skill_router as sr

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "skill_router_parity.json").read_text())

SKILLS = {
    "seo": {"name": "seo", "description": "SEO audits and keyword research.", "body": "Run an SEO audit. " * 20},
    "web-perf": {"name": "web-perf", "description": "Make a website load faster.", "body": "Core Web Vitals. " * 20},
    "session-handoff": {"name": "session-handoff", "description": "Hand off this session.", "body": "Write it. " * 400},
}


def _cat():
    return sr.build_catalogue(SKILLS)


def _jev_picking(label, confidence=0.9):
    calls = []

    def jev(payload):
        calls.append(payload)
        options = payload["questions"]["skill"]["criteria"]
        probs = {k: 0.0 for k in options}
        probs[label] = 1.0
        return {"answers": {"skill": {"type": "choice", "choice": label, "probabilities": probs,
                                      "confidence": confidence}},
                "usage": {"input_tokens": 1000}}

    jev.calls = calls
    return jev


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda c: c["query"])
def test_scoring_matches_the_library_scorer(case):
    items = [sr.Candidate.from_parts(i["name"], i["description"], i["bodyForScoring"]) for i in FIXTURE["items"]]
    q = case["query"].lower().strip()
    assert sorted(sr.query_tokens(q)) == case["tokens"]
    for item in items:
        assert sr.score(item, sr.query_tokens(q), q) == pytest.approx(case["scores"][item.name], abs=1e-9)


def test_exact_router_phrase_pins_without_a_model_call():
    jev = _jev_picking("seo")
    d = sr.route("hand off this session", catalogue=_cat(), skills=SKILLS, jev=jev,
                 pins={"hand off this session": "session-handoff"})
    assert d.source == "pin" and d.skills == ["session-handoff"] and jev.calls == []


def test_jev_pick_loads_only_that_body():
    jev = _jev_picking("web-perf")
    d = sr.route("my website is slow to load", catalogue=_cat(), skills=SKILLS, jev=jev)
    assert d.source == "jev" and d.skills == ["web-perf"]
    assert d.bodies == [SKILLS["web-perf"]["body"]]
    assert "Run an SEO audit" not in "".join(d.bodies)
    assert set(jev.calls[0]["questions"]["skill"]["criteria"]) >= {"web-perf", sr.NO_MATCH}


def test_no_match_loads_nothing():
    jev = _jev_picking(sr.NO_MATCH)
    d = sr.route("website weather forecast", catalogue=_cat(), skills=SKILLS, jev=jev)
    assert jev.calls, "the request must reach Jev for this test to mean anything"
    assert d.skills == [] and d.bodies == [] and d.source == "jev" and d.reason == "no_match"


def test_low_confidence_loads_nothing():
    d = sr.route("website audit", catalogue=_cat(), skills=SKILLS, jev=_jev_picking("seo", confidence=0.2),
                 min_confidence=0.5)
    assert d.skills == [] and d.reason == "low_confidence"


def test_jev_failure_falls_back_to_lexical_and_says_so():
    def broken(payload):
        raise TimeoutError("jev timed out")

    d = sr.route("website load faster", catalogue=_cat(), skills=SKILLS, jev=broken)
    assert d.source == "lexical_fallback" and d.skills == ["web-perf"] and "TimeoutError" in d.reason


def test_malformed_jev_answer_is_a_failure_not_a_pick():
    def bad(payload):
        return {"answers": {"skill": {"type": "choice", "choice": "seo", "probabilities": {"seo": 0.4},
                                      "confidence": 0.9}}, "usage": {"input_tokens": 10}}

    d = sr.route("website load faster", catalogue=_cat(), skills=SKILLS, jev=bad)
    assert d.source == "lexical_fallback" and d.reason == "jev_error:ValueError"


def test_no_jev_configured_falls_back_to_lexical_and_says_so():
    d = sr.route("website load faster", catalogue=_cat(), skills=SKILLS, jev=None)
    assert d.source == "lexical_fallback" and d.reason == "jev_unavailable"


def test_body_is_cut_to_the_token_budget():
    d = sr.route("hand off this session now", catalogue=_cat(), skills=SKILLS, jev=_jev_picking("session-handoff"),
                 budget_tokens=100)
    assert d.skills == ["session-handoff"]
    assert d.tokens <= 100 and d.bodies[0].endswith(sr.CUT_MARK)


ROUTER_INDEX = """# Skills Index

| Intent / trigger phrase | Skill |
|---|---|
| "hand off this session" / "/session-handoff" | `session-handoff` |
| "SEO" / "keyword research" · "site speed" | `seo` · `web-perf` |
| "one" / "two" | `seo` · `web-perf` |
| "audit\\|critique" | `seo` |

| Intent | Skill |
|---|---|
| "late table" | `web-perf` |
"""


def test_router_pins_read_the_one_table_like_the_library_does():
    """Port of skill_shelf.mjs routerTable/rowGroups/routerExact (rounds 4 and 10 of the library review)."""
    pins = sr.router_pins(ROUTER_INDEX)
    assert pins["hand off this session"] == "session-handoff" and pins["/session-handoff"] == "session-handoff"
    assert pins["seo"] == "seo" and pins["keyword research"] == "seo" and pins["site speed"] == "web-perf"
    assert "one" not in pins and "two" not in pins  # groups do not pair: pin nothing
    assert pins["audit|critique"] == "seo"  # an escaped pipe stays inside its cell
    assert "late table" not in pins  # only the first table routes
    assert sr.router_pins("no table here") == {}


@pytest.mark.parametrize("body,js_score", [
    ("\U0001F600" * 4000 + " target" + "\U0001F600" * 1000, 0),
    ("\U0001F600" * 3999 + " target" + " tail", 0),
    ("a" * 7990 + " target", 6.447213595499958),
    ("\U0001F600" * 3997 + "x target", 0),
])
def test_body_prefix_is_cut_in_utf16_units_like_lib_mjs(body, js_score):
    """Review P1-SCORER-UTF16-PREFIX-DIVERGENCE. js_score is lib.mjs scoreItem's output for the same
    item under Node 22 (body.slice(0, 8000) counts UTF-16 units, so an emoji is 2)."""
    c = sr.Candidate.from_parts("demo", "A demo skill.", body)
    assert sr.score(c, sr.query_tokens("target"), "target") == pytest.approx(js_score)


def test_a_pin_whose_skill_is_not_loaded_here_loads_nothing_and_says_so():
    """Review P1-PRODUCTION-CATALOGUE-DROPS-LOCKED-PIN-TARGETS: it fell through to a lexical guess."""
    d = sr.route("quality checks failed", catalogue=_cat(), skills=SKILLS, jev=_jev_picking("seo"),
                 pins={"quality checks failed": "ci-quality-parity"})
    assert d.skills == [] and d.source == "none" and d.reason == "pin_target_unavailable:ci-quality-parity"


@pytest.mark.parametrize("budget", [0, 1, 2, 3, 5, 7, 8, 9, 20])
def test_a_budget_too_small_for_the_cut_mark_is_never_exceeded(budget):
    d = sr.route("hand off this session now", catalogue=_cat(), skills=SKILLS, jev=_jev_picking("session-handoff"),
                 budget_tokens=budget)
    assert d.tokens <= budget


def test_nothing_scores_means_no_call_and_no_skill():
    jev = _jev_picking("seo")
    d = sr.route("zzzz qqqq", catalogue=_cat(), skills=SKILLS, jev=jev)
    assert d.skills == [] and d.source == "none" and jev.calls == []


def test_catalogue_holds_search_text_only_never_a_loadable_body():
    """Scoring reads the first BODY_SCORE_CHARS (as the library scorer does); bodies are loaded
    per request only for chosen skills."""
    long = {"big": {"name": "big", "description": "d", "body": "x" * (sr.BODY_SCORE_CHARS * 2)}}
    (c,) = sr.build_catalogue(long)
    assert not hasattr(c, "body")
    assert len(c.haystack) <= len("big\nd\n") + sr.BODY_SCORE_CHARS
