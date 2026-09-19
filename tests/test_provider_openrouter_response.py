"""OpenRouter response parsing retains Main reasoning-model handling."""
from app.server import provider_openrouter as POR

def test_extract_text_from_well_formed_response():
    response = {
        "choices": [{"message": {"content": "hello back"}}],
    }
    assert POR._extract_text(response) == "hello back"


def test_extract_text_handles_missing_choices():
    assert POR._extract_text({}) == ""
    assert POR._extract_text({"choices": []}) == ""


def test_extract_text_falls_back_to_reasoning_when_content_is_null():
    """The measured DeepInfra/GLM shape: clean stop, null content, real answer."""
    response = {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": None, "reasoning": '{"intent":"ticket"}'},
        }],
    }
    assert POR._extract_text(response) == '{"intent":"ticket"}'


def test_extract_text_prefers_content_over_reasoning():
    """When both are present, content is the answer and reasoning is the trace."""
    response = {
        "choices": [{
            "message": {"content": "the answer", "reasoning": "step 1, step 2"},
        }],
    }
    assert POR._extract_text(response) == "the answer"


def _extract_text_of(response):
    return POR._extract_text(response)


def test_extract_text_ignores_reasoning_when_response_was_truncated():
    """A truncated trace is a partial thought, not an answer.

    finish_reason "length" means the token budget ran out mid-reasoning.
    Measured on glm-4.7-flash at max_tokens=120: reasoning held
    '1.  **Analyze the Request:** ...' and content was null. Returning that
    would hand the caller a chain-of-thought dressed as a result.
    """
    response = {
        "choices": [{
            "finish_reason": "length",
            "message": {
                "content": None,
                "reasoning": "1.  **Analyze the Request:** the user wants",
            },
        }],
    }
    assert _extract_text_of(response) == ""


def test_extract_text_ignores_reasoning_on_any_unclean_finish():
    """Allowlist, not denylist — "length" is not the only unfinished state.

    content_filter, error, or a reason a provider invents next quarter all mean
    the model did not finish saying this, so the trace is not an answer.
    """
    for finish in ("content_filter", "error", "tool_calls", "some_new_reason"):
        response = {
            "choices": [{
                "finish_reason": finish,
                "message": {"content": None, "reasoning": "partial thought"},
            }],
        }
        assert POR._extract_text(response) == "", finish


def test_extract_text_ignores_reasoning_when_finish_reason_is_absent():
    """Silence is not proof the model finished.

    A provider that never reports finish_reason gives us no evidence the trace
    is complete, so it does not earn the fallback. Returning a possibly-partial
    thought as the answer would be a failed read dressed as a successful one;
    an empty string reaches the caller honestly as openrouter_empty_response.
    """
    response = {
        "choices": [{"message": {"content": None, "reasoning": '{"intent":"ticket"}'}}],
    }
    assert POR._extract_text(response) == ""


def test_extract_text_uses_reasoning_when_model_finished():
    """The same shape with a clean stop IS the answer, so it must come back."""
    response = {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": None, "reasoning": '{"intent":"ticket"}'},
        }],
    }
    assert _extract_text_of(response) == '{"intent":"ticket"}'


def test_extract_text_empty_when_neither_content_nor_reasoning():
    """Both empty must still be empty — the fallback must not invent text.

    This is the case that still has to reach the caller as
    openrouter_empty_response.
    """
    assert POR._extract_text({"choices": [{"message": {}}]}) == ""
    assert POR._extract_text(
        {"choices": [{"message": {"content": None, "reasoning": None}}]},
    ) == ""
    assert POR._extract_text(
        {"choices": [{"message": {"content": "", "reasoning": ""}}]},
    ) == ''


def test_extract_cost_usd_from_usage_block():
    response = {"usage": {"cost": 0.000123}}
    assert POR._extract_cost_usd(response) == 0.000123


def test_extract_cost_usd_falls_back_to_total_cost():
    response = {"usage": {"total_cost": 0.5}}
    assert POR._extract_cost_usd(response) == 0.5


def test_extract_cost_usd_zero_when_absent():
    assert POR._extract_cost_usd({}) == 0.0
    assert POR._extract_cost_usd({"usage": {}}) == 0.0


def test_extract_cost_usd_handles_garbage():
    response = {"usage": {"cost": "not-a-number"}}
    assert POR._extract_cost_usd(response) == 0.0
