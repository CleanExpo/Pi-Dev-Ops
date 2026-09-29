"""The only Gemini request shape the reservation prices (release review r8, fixed as a class).

`gemini.call` sends a body only when it has exactly the shape `request_body` builds: text, function-call
and function-response turns, an optional text system instruction, function declarations, and
generationConfig of one reply bounded by maxOutputTokens at the fixed thinking level. Anything else
(grounding or code-execution tools, cached content, extra replies, a setting Google adds later) could
bill outside `reserve_generate`, so it is refused before any request. An allow-list, never a deny-list.
"""
from __future__ import annotations

TOP_LEVEL = {"model", "contents", "generationConfig", "systemInstruction", "tools"}
PART_KEYS = {"text", "thought", "thoughtSignature", "functionCall", "functionResponse"}
ROLES = {"user", "model"}


def _parts_ok(parts, keys: set) -> bool:
    return isinstance(parts, list) and bool(parts) and all(isinstance(p, dict) and set(p) <= keys for p in parts)


def problem(body, max_output_tokens: int, thinking_level: str) -> str | None:
    """None when `body` is priced exactly; otherwise the reason it is refused."""
    if not isinstance(body, dict):
        return "body is not an object"
    cfg = body.get("generationConfig")
    if not isinstance(cfg, dict) or set(cfg) != {"maxOutputTokens", "thinkingConfig"} \
            or cfg["maxOutputTokens"] not in range(1, max_output_tokens + 1) or isinstance(cfg["maxOutputTokens"], bool) \
            or cfg["thinkingConfig"] != {"thinkingLevel": thinking_level}:
        return (f"maxOutputTokens 1..{max_output_tokens} and thinkingLevel {thinking_level!r} are the only "
                "generation settings")
    if extra := set(body) - TOP_LEVEL:
        return f"unpriced body keys {sorted(extra)}"
    if "model" in body and not isinstance(body["model"], str):
        return "model is not a string"
    contents = body.get("contents")
    if not isinstance(contents, list) or not contents or not all(
            isinstance(c, dict) and set(c) == {"role", "parts"} and c["role"] in ROLES and _parts_ok(c["parts"], PART_KEYS)
            for c in contents):
        return "contents must be user/model turns of text or function parts"
    if "systemInstruction" in body and not (isinstance(body["systemInstruction"], dict)
                                            and set(body["systemInstruction"]) == {"parts"}
                                            and _parts_ok(body["systemInstruction"]["parts"], {"text"})):
        return "systemInstruction must be text parts"
    tools = body.get("tools", [])
    if not isinstance(tools, list) or not all(isinstance(t, dict) and set(t) == {"functionDeclarations"} for t in tools):
        return "tools may only declare functions"
    return None
