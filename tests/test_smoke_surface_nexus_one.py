"""tests/test_smoke_surface_nexus_one.py — the smoke expectation matches the real response.

Production smoke looked for '"registered": false' (with a space) from 13/09; FastAPI
serialises compactly, so the check could never pass against a correct deployment.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.nexus_one.status import synthetic_status

SURFACES = Path(__file__).resolve().parents[1] / ".github" / "smoke-surfaces.json"


def test_every_expected_string_is_in_the_served_payload():
    app = FastAPI()
    app.get("/status")(lambda: synthetic_status(registered=False))
    body = TestClient(app).get("/status").text
    entry = next(s for s in json.loads(SURFACES.read_text())["horizontal"]
                 if s.get("name") == "api-nexus-one-status")
    assert [s for s in entry["body_contains"] if s not in body] == []
