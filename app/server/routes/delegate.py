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

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured on server")

    # Use Sonnet (mid-tier) for all delegation tasks — avoids session_sdk /
    # Claude Code CLI which requires interactive login unavailable on Railway.
    model = os.environ.get("TAO_MID_MODEL", "claude-sonnet-4-6").strip()

    prompt = (
        f"[RA-1631 Delegation · job={job_id} · agent={agent_name} · chat={body.chat_id}]\n\n"
        f"{body.spec}"
    )

    def _call_anthropic() -> tuple[str, float]:
        import anthropic as _anthropic  # noqa: PLC0415
        client = _anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            timeout=55.0,
        )
        text = message.content[0].text if message.content else ""
        usage = message.usage
        input_tok = getattr(usage, "input_tokens", 0)
        output_tok = getattr(usage, "output_tokens", 0)
        # Approximate cost: Sonnet ~$3/$15 per 1M in/out tokens
        cost = (input_tok * 3 + output_tok * 15) / 1_000_000
        return text, cost

    try:
        text, cost_usd = await asyncio.wait_for(
            asyncio.to_thread(_call_anthropic),
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
