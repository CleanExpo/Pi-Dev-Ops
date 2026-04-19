# Implementation Plan

**Session:** c15604cc4848  
**Confidence:** 42%

**Risk notes:** Brief does not specify which bug to fix — no error message, no reproduction steps, no ticket number provided. Assumptions made from lessons-learned warnings: previous session scored 1/10 completeness on webhook event-mapping work (event_dispatcher.py, cin7_models.py, webhooks.py referenced). Those files may not exist in this repo under those exact names; the plan targets the confirmed webhook route at app/server/routes/webhooks.py and app/server/models.py. If the actual bug is in a different subsystem (sessions, pipeline, auth), units 1-2 will redirect once the reproduce step reads current logs. Confidence is low because the brief is ambiguous; the reproduce unit must be executed first to confirm the actual failure condition before any fix is applied.

## Unit 1: Reproduce and diagnose the bug — read logs, trace failure condition
**Files:** `app/server/routes/webhooks.py`, `app/server/models.py`, `app/server/app_factory.py`
**Test scenarios:**
  - happy path: POST /api/webhook with valid GitHub push payload returns 200 and triggers session
  - edge case: POST /api/webhook with Linear event payload routes correctly without 500
  - edge case: webhook with missing or malformed signature returns 401 not 500

## Unit 2: Fix webhook event routing — ensure all event types are handled without unhandled exceptions
**Files:** `app/server/routes/webhooks.py`
**Test scenarios:**
  - happy path: GitHub push event to non-pidev/ branch dispatches session correctly
  - edge case: GitHub push to pidev/ branch is silently skipped (no recursive loop)
  - edge case: unknown event type returns 200 with ignored status, not 500
  - edge case: Linear issue state-change event routes to correct team/project via projects.json

## Unit 3: Fix or add missing Pydantic request models for webhook payloads
**Files:** `app/server/models.py`
**Test scenarios:**
  - happy path: webhook payload with all required fields deserialises without ValidationError
  - edge case: optional fields absent do not raise, return None gracefully

## Unit 4: Smoke-test gate — py_compile all edited Python files and run pytest
**Files:** `app/server/routes/webhooks.py`, `app/server/models.py`, `tests/`
**Test scenarios:**
  - happy path: python -m py_compile on every edited file exits 0
  - happy path: pytest tests/ -x -q passes with at most 3 pre-existing failures in test_sdk_phase2.py
  - edge case: import check python -c 'from app.server.main import app' prints FastAPI without ImportError

## Unit 5: Conventional commit — stage and write commit message (fix: ...)
**Files:** `app/server/routes/webhooks.py`, `app/server/models.py`
