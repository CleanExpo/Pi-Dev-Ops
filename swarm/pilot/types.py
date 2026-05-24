"""Shared types for the Pilot suggestion pipeline.

Per ADR 001: pillar is list[str] (array-typed) from day one — never str.
Per ADR 002: tenant_slug is the isolation boundary.
"""
from dataclasses import dataclass
from typing import Any, Literal

Effort = Literal["XS", "S", "M", "L"]
Source = Literal["wiki", "linear", "margot", "gmail", "github", "agent-derived"]
Confidence = Literal["LOW", "MED", "HIGH"]


@dataclass
class RawCandidate:
    fingerprint: str
    headline: str
    pillar: list[str]      # ≥1 per ADR 001 — array-typed from day one
    effort: Effort
    source: Source
    confidence: Confidence
    body: dict[str, Any]
    impact_score: int      # 0-100
