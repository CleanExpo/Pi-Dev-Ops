"""RA-8408 — structural guards for the X-Pi-CEO-Secret owner.

AC-3: only config.py and internal_secret.py name the fleet-key variables, and secret
comparisons happen only in an explicit allow-list of files. Matching is exact equality
on syntax-tree nodes, never a substring, so pinned error texts and other secrets'
names are not findings.
AC-4: every route that takes the header, enumerated from the real routers, is in the
route table that tests/test_internal_secret_routes.py proves.
AC-11: the GitHub signature path is untouched by the next key.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import importlib
import inspect
import pkgutil
import sys
import textwrap
from pathlib import Path
from typing import Optional

import pytest
from fastapi import APIRouter, FastAPI, Header, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
NAMES = {"INTERNAL_WEBHOOK_SECRET", "WEBHOOK_SECRET"}
STRINGS = NAMES | {"TAO_INTERNAL_WEBHOOK_SECRET", "TAO_INTERNAL_WEBHOOK_SECRET_NEXT",
                   "TAO_WEBHOOK_SECRET", "TAO_FLEET_READ_SECRET"}
OWNERS = {"app/server/config.py", "app/server/internal_secret.py"}
# Files that compare some other secret today (GitHub/Linear signatures, intake, Gmail,
# calendar, Telegram, Slack, Nexus webhooks, the dashboard password), plus the owner.
COMPARERS = {"app/server/auth.py", "app/server/webhook.py", "app/server/internal_secret.py",
             "app/server/routes/health.py", "app/server/routes/nexus.py", "app/server/routes/slack_bridge.py",
             "app/server/routes/telegram_webhook_secret.py", "app/server/routes/webhooks.py"}
HELPER = "_require_internal_webhook_secret"
EXPECTED_ROUTES = {
    ("POST", "/api/conversations/ingest"), ("GET", "/api/conversations/search"), ("GET", "/api/conversations/recent"),
    ("GET", "/api/cost-report"), ("GET", "/api/routing"), ("POST", "/api/margot/delegate"),
    ("POST", "/api/margot/turn"), ("POST", "/api/margot/voice"),
    ("POST", "/api/mesh/heartbeat"), ("GET", "/api/mesh/claims"), ("POST", "/api/mesh/claim/update"),
    ("POST", "/api/mesh/claims/reap"), ("POST", "/api/mesh/dispatch"), ("POST", "/api/mesh/claim/self"),
    ("POST", "/api/mesh/lane-events"), ("POST", "/api/mesh/ship"),
    ("POST", "/api/webhook/morning-intel"), ("POST", "/api/webhook/routine-complete"),
    ("POST", "/api/webhook/workspace-intel-refresh"), ("GET", "/api/workspace-intel"),
    ("POST", "/api/wiki/sources/upload"), ("GET", "/api/wiki/sources"), ("GET", "/api/wiki/requirements"),
    ("PUT", "/api/wiki/requirements"), ("GET", "/api/mesh/fleet"), ("GET", "/api/mesh/lane-events")}


@pytest.fixture(autouse=True, scope="module")
def _import_neutral():
    """Leave app.server.routes as found: other test files re-import route modules by name."""
    before = {name for name in sys.modules if name.startswith("app.server.routes.")}
    yield
    package = sys.modules.get("app.server.routes")
    for name in [n for n in sys.modules if n.startswith("app.server.routes.") and n not in before]:
        sys.modules.pop(name, None)
        if package is not None and hasattr(package, name.rsplit(".", 1)[1]):
            delattr(package, name.rsplit(".", 1)[1])


# ── AC-3 ─────────────────────────────────────────────────────────────────────
def references(source: str) -> list[str]:
    """Every node naming a fleet-key variable, by exact equality."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and node.id in NAMES:
            found.append(f"name {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in NAMES:
            found.append(f"attribute {node.attr}")
        elif isinstance(node, ast.alias) and {node.name, node.asname} & NAMES:
            found.append(f"import {node.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in STRINGS:
            found.append(f"string {node.value}")
    return found


def compare_sites(source: str) -> int:
    """compare_digest calls, by attribute or bare name, plus imports of it under any alias."""
    count = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            count += getattr(func, "attr", getattr(func, "id", None)) == "compare_digest"
        elif isinstance(node, ast.alias):
            count += node.name == "compare_digest"
    return count


def scan(root: Path) -> tuple[dict[str, list[str]], set[str]]:
    refs, comparers = {}, set()
    for path in sorted((root / "app/server").rglob("*.py")):
        rel, text = path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")
        if rel not in OWNERS and (found := references(text)):
            refs[rel] = found
        if compare_sites(text):
            comparers.add(rel)
    return refs, comparers


def test_ac03_no_fleet_key_reference_outside_the_owner():
    refs, _ = scan(ROOT)
    assert refs == {}


def test_ac03_secret_comparisons_only_in_allowed_files():
    _, comparers = scan(ROOT)
    assert comparers <= COMPARERS, comparers - COMPARERS
    assert "app/server/internal_secret.py" in comparers
    assert "app/server/mesh_fleet_auth.py" not in comparers


def test_ac07_mesh_fleet_auth_holds_no_compare_of_its_own():
    tree = ast.parse((ROOT / "app/server/mesh_fleet_auth.py").read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert not names & {"compare_digest", "hmac", "hashlib", "environ", "INTERNAL_WEBHOOK_SECRET"}
    assert "classify_fleet_read" in names


def test_ac03_scan_of_the_two_owner_files_is_non_empty():
    for rel in sorted(OWNERS):
        assert references((ROOT / rel).read_text(encoding="utf-8")), rel


PLANTED = {"attribute": "from . import config\nKEY = config.INTERNAL_WEBHOOK_SECRET\n",
           "import": "from .config import INTERNAL_WEBHOOK_SECRET as key\n",
           "getattr": "from . import config\nKEY = getattr(config, 'INTERNAL_WEBHOOK_SECRET')\n",
           "environ": "import os\nKEY = os.environ.get('TAO_INTERNAL_WEBHOOK_SECRET_NEXT', '')\n"}


@pytest.mark.parametrize("source", list(PLANTED.values()), ids=list(PLANTED))
def test_ac03_planted_reference_forms_are_found(source, tmp_path):
    (tmp_path / "app/server").mkdir(parents=True)
    (tmp_path / "app/server/planted.py").write_text(source)
    refs, _ = scan(tmp_path)
    assert list(refs) == ["app/server/planted.py"]


def test_ac03_planted_compare_site_in_a_new_file_is_found(tmp_path):
    (tmp_path / "app/server/routes").mkdir(parents=True)
    (tmp_path / "app/server/routes/planted.py").write_text("import hmac\nok = hmac.compare_digest(a, b)\n")
    (tmp_path / "app/server/aliased.py").write_text("from hmac import compare_digest as same\n")
    _, comparers = scan(tmp_path)
    assert comparers == {"app/server/routes/planted.py", "app/server/aliased.py"}
    assert not comparers <= COMPARERS


def test_ac03_pinned_texts_and_other_secret_names_are_not_found():
    source = ("from . import config\nimport os\n"
              "raise HTTPException(503, 'TAO_INTERNAL_WEBHOOK_SECRET not configured on server')\n"
              "a = config.GITHUB_WEBHOOK_SECRET\nb = os.environ.get('TAO_GITHUB_WEBHOOK_SECRET')\n"
              "c = 'STRIPE_WEBHOOK_SECRET'\nd = config.INTAKE_WEBHOOK_SECRET\n")
    assert references(source) == []


# ── AC-4 ─────────────────────────────────────────────────────────────────────
def _takes_header(dependant) -> bool:
    if any((p.alias or p.name).lower() == "x-pi-ceo-secret" for p in dependant.header_params):
        return True
    return any(_takes_header(dep) for dep in dependant.dependencies)


def _calls_helper(endpoint) -> bool:
    tree = ast.parse(textwrap.dedent(inspect.getsource(endpoint)))
    return any(isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == HELPER
               for n in ast.walk(tree))


def enumerate_routes(routers) -> set[tuple[str, str]]:
    found = set()
    for router in routers:
        for route in router.routes:
            if isinstance(route, APIRoute) and (_takes_header(route.dependant) or _calls_helper(route.endpoint)):
                found |= {(method, route.path) for method in route.methods}
    return found


def _real_routers() -> list[APIRouter]:
    package = importlib.import_module("app.server.routes")
    routers = []
    for info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"app.server.routes.{info.name}")  # an import failure fails the test
        routers += [value for value in vars(module).values() if isinstance(value, APIRouter)]
    return routers


def test_ac04_every_route_taking_the_header_is_in_the_tested_table():
    assert enumerate_routes(_real_routers()) == EXPECTED_ROUTES


def test_ac04_the_route_test_file_proves_exactly_that_table():
    source = (ROOT / "tests/test_internal_secret_routes.py").read_text(encoding="utf-8")
    table = next(n.value for n in ast.parse(source).body
                 if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "ROUTES")
    assert {(row.elts[2].value, row.elts[3].value) for row in table.elts} == EXPECTED_ROUTES


def test_ac04_a_planted_route_makes_the_enumeration_fail():
    planted = APIRouter()

    @planted.post("/api/planted/header")
    def by_header(x_pi_ceo_secret: Optional[str] = Header(default=None, alias="X-Pi-CEO-Secret")):
        return {}

    @planted.get("/api/planted/helper")
    def by_helper(request: Request):
        _require_internal_webhook_secret(request)  # noqa: F821 — only parsed, never called

    found = enumerate_routes(_real_routers() + [planted])
    assert found - EXPECTED_ROUTES == {("POST", "/api/planted/header"), ("GET", "/api/planted/helper")}
    assert found != EXPECTED_ROUTES


# ── AC-11 ────────────────────────────────────────────────────────────────────
def test_ac11_github_signature_ignores_the_next_key(monkeypatch):
    from app.server import config, internal_secret
    from app.server.auth import require_rate_limit
    from app.server.routes import webhooks
    github, current, nxt = ("fake-github-signing-key-gggggggggggg", "fake-current-key-aaaaaaaaaaaaaaaaaaaaaa",
                            "fake-next-key-bbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    monkeypatch.setattr(config, "GITHUB_WEBHOOK_SECRET", github)
    monkeypatch.setattr(config, "INTERNAL_WEBHOOK_SECRET", current)
    monkeypatch.setenv(internal_secret.NEXT_ENV, nxt)
    monkeypatch.delenv(internal_secret.READ_ONLY_ENV, raising=False)
    assert internal_secret.classify(nxt, "webhooks") == "next"
    app = FastAPI()
    app.include_router(webhooks.router)
    app.dependency_overrides[require_rate_limit] = lambda: True
    client, body = TestClient(app), b'{"zen": "fake"}'

    def send(key: str):
        sig = "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
        return client.post("/api/webhook", content=body, headers={"x-github-event": "ping", "x-hub-signature-256": sig})
    for key in (nxt, current):
        refused = send(key)
        assert (refused.status_code, refused.json()["detail"]) == (401, "Invalid signature")
    accepted = send(github)
    assert accepted.status_code == 200 and accepted.json()["skipped"] is True
