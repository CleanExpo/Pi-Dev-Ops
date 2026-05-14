"""swarm/inbox/preamble_trainer.py — daily self-training for ContextBot contexts.

The point: every conversation Phill (or a client) has with a ContextBot
is training signal. The swarm shouldn't just file messages — it should
learn the *flavour* of each context (vocabulary, recurring concerns,
preferred response style, urgency signals) and then use that flavour as
grounded system context for every future agent action in that context.

Runs daily at 02:00 AEST via LaunchAgent. For each context with messages
in the last `WINDOW_HOURS` (default 24):

1. Pull last N messages from `context_bot_messages` (most recent first).
2. Build a Gemini prompt that asks for a *short operating preamble*
   focusing on: vocabulary, recurring topics, urgency markers, preferred
   reply tone. Keep under 600 words.
3. Write the preamble to
   `~/2nd Brain/2nd Brain/Wiki/contexts/<context_id>/preamble.md`
   with a header pointing at the source context_bot.
4. Update the wiki index so Margot/the swarm can find it.

The preamble file is then loaded as system context by future agents
acting on this context (e.g. when filing a new ticket from a new message,
they prepend the preamble to the model prompt).

Public API:
    train(*, dry_run: bool = False, window_hours: int = 24,
          max_messages: int = 80) -> dict
        Run one full training cycle. Returns {contexts_seen,
        preambles_written, errors, dry_run}.
"""
from __future__ import annotations

import json
import logging
import os
import re
import textwrap
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.inbox.preamble_trainer")

AEST = timezone(timedelta(hours=10))
DEFAULT_WINDOW_HOURS = 24
DEFAULT_MAX_MESSAGES = 80
DEFAULT_MODEL = os.environ.get("MARGOT_RESEARCH_MODEL", "gemini-2.5-pro")
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
WIKI_ROOT = Path(os.environ.get(
    "BRAIN1_WIKI_ROOT",
    str(Path.home() / "2nd Brain" / "2nd Brain" / "Wiki"),
))


# ── Supabase access (reuses intake_router patterns inline to keep this module standalone) ─
def _sb_request(method: str, path: str, params: dict | None = None,
                body: Any = None, extra_headers: dict | None = None) -> Any:
    url = f"{os.environ['SUPABASE_UNITE_GROUP_URL'].rstrip('/')}/rest/v1{path}"
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    key = os.environ["SUPABASE_UNITE_GROUP_SERVICE_KEY"]
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


# ── Pull recent messages per context ────────────────────────────────────────
def list_active_contexts(*, window_hours: int) -> list[dict]:
    """Return [{context_id, context_label, wiki_section, message_count}] for any
    context with at least one message in the window."""
    since = (datetime.now(AEST) - timedelta(hours=window_hours)).isoformat()
    # PostgREST doesn't do GROUP BY directly; fetch messages and aggregate client-side.
    rows = _sb_request(
        "GET",
        "/context_bot_messages",
        params={
            "select": "context_id,received_at,id",
            "received_at": f"gte.{since}",
            "limit": 5000,
            "order": "context_id,received_at.desc",
        },
    ) or []
    by_ctx: dict[str, int] = {}
    for r in rows:
        by_ctx[r["context_id"]] = by_ctx.get(r["context_id"], 0) + 1
    if not by_ctx:
        return []
    # Join with context_bots to get label + wiki_section
    bot_rows = _sb_request(
        "GET",
        "/context_bots",
        params={
            "select": "context_id,context_label,wiki_section",
            "context_id": f"in.({','.join(by_ctx.keys())})",
        },
    ) or []
    seen = set()
    out = []
    for b in bot_rows:
        if b["context_id"] in seen:
            continue
        seen.add(b["context_id"])
        out.append({
            "context_id": b["context_id"],
            "context_label": b["context_label"],
            "wiki_section": b.get("wiki_section"),
            "message_count": by_ctx[b["context_id"]],
        })
    return out


def fetch_messages(context_id: str, *, max_messages: int) -> list[dict]:
    rows = _sb_request(
        "GET",
        "/context_bot_messages",
        params={
            "select": "from_username,from_name,body,received_at",
            "context_id": f"eq.{context_id}",
            "order": "received_at.desc",
            "limit": max_messages,
        },
    ) or []
    return rows


# ── Gemini call (no grounding — pure summarisation) ─────────────────────────
def _gemini_api_key() -> str:
    return os.environ["GEMINI_API_KEY"]


def _gemini_summarise(prompt: str, *, model: str = DEFAULT_MODEL,
                      max_tokens: int = 2000, timeout: int = 60) -> str:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": max_tokens,
        },
    }
    url = f"{GEMINI_API}/models/{model}:generateContent?key={_gemini_api_key()}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.loads(r.read())
    candidates = raw.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"empty Gemini response: {raw}")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


def build_prompt(context: dict, messages: list[dict]) -> str:
    """Assemble the prompt that asks Gemini for the operating preamble.

    v2 (2026-05-14) — extends the prose preamble with a structured
    typed-entity JSON block at the end. This directly attacks the
    rediscovery-cost problem identified in `[[research-pinecone-knowledge-layer]]`:
    downstream agents can load `preamble.json` and skip re-parsing the
    Markdown narrative when they only need entities.
    """
    lines: list[str] = []
    for m in reversed(messages):  # chronological order in prompt
        sender = m.get("from_username") or m.get("from_name") or "anon"
        ts = m["received_at"]
        body = (m.get("body") or "").strip()
        lines.append(f"[{ts}] @{sender}: {body}")
    transcript = "\n".join(lines)
    return textwrap.dedent(f"""\
        You are writing an *operating preamble* — a short briefing that a downstream
        AI agent will load as system context before responding to this person/context
        in the future. Your job is to capture the flavour of how they communicate, NOT
        to summarise individual messages.

        Context: **{context['context_label']}** (id: `{context['context_id']}`)

        Last {len(messages)} messages, oldest first:
        ---
        {transcript}
        ---

        Write the preamble as Markdown with these sections (keep prose under 600 words):

        ## Vocabulary
        Words, acronyms, project names, product names this person uses. Definitions
        the agent will need.

        ## Recurring topics
        Bulleted list of what they keep bringing up. Group related items.

        ## Communication style
        Tone (formal/casual), length preference (terse/detailed), how they signal
        urgency, how they signal approval/disapproval. Note any explicit preferences
        ("don't summarise", "always cite", etc.).

        ## Active commitments
        Outstanding asks the agent should remember (e.g. "Phill expects the floor
        plan workstream done by Tue 26 May").

        ## Red flags
        Things the agent must NOT do based on past corrections.

        After the Markdown sections, append a fenced JSON block (```json ... ```)
        with the same content RE-EXPRESSED as typed entities. This is the
        machine-readable surface — downstream agents load it WITHOUT re-parsing
        the prose. Schema:

        ```json
        {{
          "people":      [{{"name": "...", "role": "...", "first_seen": "<ts>", "confirmed": true}}],
          "decisions":   [{{"summary": "...", "decided_at": "<ts>", "owner": "...", "confirmed": true|false}}],
          "deadlines":   [{{"item": "...", "due": "<YYYY-MM-DD>", "owner": "...", "confirmed": true|false}}],
          "blockers":    [{{"item": "...", "blocked_on": "...", "since": "<ts>", "severity": "low|med|high"}}],
          "commitments": [{{"who": "...", "what": "...", "by": "<ts or 'open'>", "source_msg_ts": "<ts>"}}]
        }}
        ```

        Rules for the JSON block:
        - Every entity MUST have a `confirmed` boolean (true = explicit in transcript;
          false = inferred). Inferred entities are useful but flagged.
        - Use ISO 8601 timestamps where possible. If only a date is known, `YYYY-MM-DD`.
        - Empty arrays are valid — emit `"people": []` rather than omitting the key.
        - Do NOT invent entities not supported by the transcript.

        Output ONLY the Markdown + the JSON fence. No preamble, no closing remarks.
        Use direct facts; do not hedge with "likely" or "possibly".
    """)


# ── Parse the Gemini response into (markdown, entities_json) ────────────────
_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def split_preamble_and_entities(response: str) -> tuple[str, dict]:
    """Split Gemini output into the prose preamble and the typed-entity JSON.

    Returns (markdown_body, entities_dict). If no JSON fence is found, returns
    (full_response, empty_dict_with_canonical_keys). The caller still gets a
    valid prose preamble — the JSON is an additive surface, not a hard
    requirement.
    """
    canonical_keys = {
        "people": [], "decisions": [], "deadlines": [],
        "blockers": [], "commitments": [],
    }
    match = _JSON_FENCE_RE.search(response)
    if not match:
        return response.strip(), dict(canonical_keys)
    try:
        entities = json.loads(match.group(1))
    except json.JSONDecodeError:
        log.warning("entities JSON failed to parse; falling back to empty")
        return response[:match.start()].strip(), dict(canonical_keys)
    # Ensure all canonical keys are present even if Gemini omitted any
    for k, default in canonical_keys.items():
        entities.setdefault(k, default)
    # Strip the fenced block out of the prose
    markdown = (response[:match.start()] + response[match.end():]).strip()
    return markdown, entities


# ── Write to wiki ───────────────────────────────────────────────────────────
def preamble_path(context_id: str) -> Path:
    return WIKI_ROOT / "contexts" / context_id / "preamble.md"


def entities_path(context_id: str) -> Path:
    return WIKI_ROOT / "contexts" / context_id / "preamble.json"


def write_preamble(context: dict, body: str, entities: dict | None = None) -> tuple[str, str | None]:
    """Write the prose preamble + the typed-entity JSON sidecar.

    Returns (preamble_path, entities_path|None). `entities` is None when the
    Gemini response had no parseable JSON fence — preamble.md still gets
    written so downstream agents always have a substrate to load.
    """
    path = preamble_path(context["context_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    header = textwrap.dedent(f"""\
        ---
        type: wiki
        updated: {datetime.now(AEST).date()}
        context_id: {context['context_id']}
        context_label: {context['context_label']}
        schema_version: preamble-v2
        ---

        # {context['context_label']} — Operating Preamble

        _Auto-generated by `swarm.inbox.preamble_trainer` at {datetime.now(AEST).isoformat()}._
        _Loaded as system context for every agent acting on this context._
        _Companion `preamble.json` holds the same content as typed entities._

        """)
    path.write_text(header + body.strip() + "\n")

    json_path: str | None = None
    if entities is not None:
        ejson = entities_path(context["context_id"])
        ejson.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "preamble-v2",
            "context_id": context["context_id"],
            "context_label": context["context_label"],
            "generated_at": datetime.now(AEST).isoformat(),
            "entities": entities,
        }
        ejson.write_text(json.dumps(payload, indent=2, default=str) + "\n")
        json_path = str(ejson)

    return str(path), json_path


# ── Main loop ───────────────────────────────────────────────────────────────
def train(*, dry_run: bool = False, window_hours: int = DEFAULT_WINDOW_HOURS,
          max_messages: int = DEFAULT_MAX_MESSAGES) -> dict:
    contexts = list_active_contexts(window_hours=window_hours)
    written = 0
    errors: list[str] = []
    for ctx in contexts:
        try:
            messages = fetch_messages(ctx["context_id"], max_messages=max_messages)
            if not messages:
                continue
            prompt = build_prompt(ctx, messages)
            if dry_run:
                log.info("dry_run: would summarise %d messages for %s",
                         len(messages), ctx["context_id"])
                continue
            raw_response = _gemini_summarise(prompt)
            preamble_body, entities = split_preamble_and_entities(raw_response)
            md_path, json_path = write_preamble(ctx, preamble_body, entities)
            log.info(
                "wrote preamble for %s → %s%s",
                ctx["context_id"], md_path,
                f" (+entities: {sum(len(v) for v in entities.values())})" if entities else " (no json)",
            )
            written += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{ctx['context_id']}: {e}")
            log.exception("preamble training failed for %s", ctx["context_id"])
    return {
        "contexts_seen": len(contexts),
        "preambles_written": written,
        "errors": errors,
        "dry_run": dry_run,
    }


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    import sys
    dry = "--dry-run" in sys.argv
    print(json.dumps(train(dry_run=dry), indent=2))
