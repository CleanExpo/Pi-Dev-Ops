"""Margot must disclose that she is synthetic, and must never claim credentials.

Founder standing rule, ~/.claude/CLAUDE.md: "Her synthetic nature is always
disclosed - on the channel, in the content, and to anyone who asks. Margot
never claims credentials. The expertise is Phill's and the content says so."

RA-7433 audit finding G06: nothing in the code enforced this. Her system
prompt carried no disclosure clause, and a search across the margot files
found "synthetic" used only for mock API providers. The rule existed only in
a document no runtime reads.

The founder's commercial asset is credibility inside an industry with a
credentialing body he helps run, so this is a sellability gate, not a style
preference.
"""
import re

from swarm import margot_bot


def _prompt():
    return margot_bot._MARGOT_SYSTEM_PROMPT


def test_the_guard_can_see_the_prompt():
    """Positive control. A guard reading an empty string passes vacuously."""
    p = _prompt()
    assert isinstance(p, str) and len(p) > 500, "system prompt did not load"
    assert "Margot" in p


def test_prompt_states_she_is_synthetic():
    """The claim must be ABOUT her, not incidental.

    A first draft of this test matched the pattern for a bare "AI " and passed
    on "the AI integration into their CRM" and "avoid AI filler words" -
    neither has anything to do with disclosure. A matcher that clears on
    unrelated prose is not a control.
    """
    p = _prompt().lower()
    assert re.search(
        r"you are (a )?synthetic|you're (a )?synthetic|synthetic presenter|"
        r"your (face|likeness|avatar) is synthetic|you are not a real person",
        p,
    ), "system prompt contains no statement that MARGOT HERSELF is synthetic"


def test_prompt_requires_disclosure_when_asked():
    p = _prompt().lower()
    assert "disclos" in p, (
        "system prompt never instructs Margot to disclose her nature; the "
        "founder rule says she discloses to anyone who asks"
    )


def test_prompt_forbids_claiming_credentials():
    p = _prompt().lower()
    assert "credential" in p, (
        "system prompt does not forbid claiming credentials; the expertise is "
        "Phill's and the content must say so"
    )


def test_disclosure_survives_into_the_built_prompt():
    """The clause must reach the text actually sent to the model.

    A constant that nothing concatenates is not a control. This asserts the
    assembled prompt, which is what the model receives.
    """
    built = margot_bot.build_prompt(
        user_text="are you a real person?", history=[], context={}
    )
    low = built.lower()
    assert "disclos" in low, "disclosure instruction missing from assembled prompt"
    assert "synthetic" in low, "synthetic statement missing from assembled prompt"
