"""Margot → Pi-CEO delegation route — RA-1631.

Margot sends a task_type + spec; this route maps to the right TAO agent
name, calls the Anthropic API directly (bypassing session_sdk / Claude Code
CLI which is not authenticated on Railway), and returns synchronously.

Auth: ``X-Pi-CEO-Secret`` header == ``TAO_WEBHOOK_SECRET``.
Same scheme as margot.py.
"""
from __future__ import annotations

import asyncio
import hmac as _hmac
import logging
import os
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import config

log = logging.getLogger("pi-ceo.routes.delegate")

router = APIRouter()

# task_type → TAO agent display name + provider role
TASK_TYPE_MAP: dict[str, tuple[str, str]] = {
    "code_gen":  ("Nova",  "generator"),
    "research":  ("Sage",  "generator"),   # margot.synthesis → opus, not allowed; generator = Sonnet
    "planning":  ("Atlas", "planner"),
    "review":    ("Lens",  "evaluator"),
    "docs":      ("Quill", "generator"),
    "ops":       ("Vex",   "monitor"),
}

VALID_TASK_TYPES = sorted(TASK_TYPE_MAP.keys())

TaskType = Literal["code_gen", "research", "planning", "review", "docs", "ops"]


class DelegateRequest(BaseModel):
    task_type: TaskType = Field(..., description="Type of work to delegate")
    spec: str = Field(..., min_length=1, max_length=8000,
                      description="Natural-language task description")
    chat_id: str = Field(..., description="Telegram chat_id for context")
    job_id: Optional[str] = Field(
        default=None,
        description="Client-supplied idempotency UUID (generated if absent)",
    )


class DelegateResponse(BaseModel):
    job_id: str
    result: str
    agent: str
    cost_usd: float
    status: Literal["complete", "error"]
    error: Optional[str]


def _check_secret(x_pi_ceo_secret: Optional[str]) -> None:
    if not config.WEBHOOK_SECRET:
        raise HTTPException(503, "TAO_WEBHOOK_SECRET not configured on server")
    if not x_pi_ceo_secret:
        raise HTTPException(401, "Missing X-Pi-CEO-Secret header")
    if not _hmac.compare_digest(x_pi_ceo_secret, config.WEBHOOK_SECRET):
        raise HTTPException(401, "Invalid X-Pi-CEO-Secret")


@router.post("/api/margot/delegate", response_model=DelegateResponse)
async def delegate_task(
    body: DelegateRequest,
    x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret"),
):
    """Receive a delegation request from Margot/Hermes and run it via TAO.

    Maps task_type → TAO agent name + provider role, then dispatches the
    spec to provider_router. Returns synchronously — no webhooks for v1.
    """
    _check_secret(x_pi_ceo_secret)

    agent_name, role = TASK_TYPE_MAP[body.task_type]
    job_id = body.job_id or str(uuid.uuid4())

    log.info(
        "delegate: job=%s task_type=%s agent=%s chat_id=%s",
        job_id, body.task_type, agent_name, body.chat_id,
    )

    # Prefer raw Anthropic API; fall back to OpenRouter (which IS set on Railway).
    # Both avoid session_sdk / Claude Code CLI which requires interactive login.
    anthropic_key = config.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")

    if not anthropic_key and not openrouter_key:
        raise HTTPException(503, "No LLM API key configured (ANTHROPIC_API_KEY or OPENROUTER_API_KEY)")

    prompt = (
        f"[RA-1631 Delegation · job={job_id} · agent={agent_name} · chat={body.chat_id}]\n\n"
        f"{body.spec}"
    )

    def _call_llm() -> tuple[str, float]:
        if anthropic_key:
            import anthropic as _anthropic  # noqa: PLC0415
            model = os.environ.get("TAO_MID_MODEL", "claude-sonnet-4-6").strip()
            client = _anthropic.Anthropic(api_key=anthropic_key)
            message = client.messages.create(
                model=model, max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
                timeout=55.0,
            )
            text = message.content[0].text if message.content else ""
            usage = message.usage
            cost = (getattr(usage, "input_tokens", 0) * 3 +
                    getattr(usage, "output_tokens", 0) * 15) / 1_000_000
            return text, cost
        else:
            # OpenRouter fallback — available on Railway via OPENROUTER_API_KEY
            import httpx  # noqa: PLC0415
            model = "anthropic/claude-sonnet-4-6"
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {openrouter_key}",
                         "Content-Type": "application/json"},
                json={"model": model, "max_tokens": 2048,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=55.0,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            cost = (usage.get("prompt_tokens", 0) * 3 +
                    usage.get("completion_tokens", 0) * 15) / 1_000_000
            return text, cost

    try:
        text, cost_usd = await asyncio.wait_for(
            asyncio.to_thread(_call_llm),
            timeout=60.0,
        )
    except asyncio.TimeoutError as exc:
        log.warning("delegate timeout job=%s", job_id)
        raise HTTPException(504, "Delegation task exceeded 60s timeout") from exc
    except Exception as exc:
        log.exception("delegate failed job=%s", job_id)
        return DelegateResponse(
            job_id=job_id,
            result="",
            agent=agent_name,
            cost_usd=0.0,
            status="error",
            error=str(exc),
        )

    return DelegateResponse(
        job_id=job_id,
        result=text,
        agent=agent_name,
        cost_usd=round(cost_usd, 6),
        status="complete",
        error=None,
    )
