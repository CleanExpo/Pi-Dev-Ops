"""UNI-2647 — backend /api/mission-control/live keys equal the TS types that read them.

The cockpit used to read `throughput.hourly_24h` while mission_control.py emits
`throughput.hourly`, and typed `actions` as `string[]` while the backend sends
objects. Those two mismatches made completed-24h vanish and rendered
`[object Object]`. This fixture walks both sources so a rename on one side
fails here, not on the live cockpit.

Written to fail against the pre-fix readers (`hourly_24h`, `actions: string[]`).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "app" / "server" / "routes" / "mission_control.py"
SESSIONS = REPO / "app" / "server" / "routes" / "mission_control_sessions.py"
ELIGIBILITY = REPO / "app" / "server" / "autonomy_eligibility.py"
TYPES = REPO / "dashboard" / "lib" / "control" / "mission-control-live.ts"
READERS = (
    REPO / "dashboard" / "components" / "control" / "LiveActivityFeed.tsx",
    REPO / "dashboard" / "app" / "(main)" / "loop" / "page.tsx",
    REPO / "dashboard" / "app" / "api" / "pi-ceo" / "[...path]" / "route.ts",
)

# Keys the cockpit actually reads. Backend may also emit claude_hud; the proxy
# may add `error`. Those extras are allowed. These must exist on BOTH sides.
COCKPIT_TOP = {
    "ts",
    "throughput",
    "active_sessions",
    "recent_completions",
    "queue",
    "pulse",
    "observability",
}


def _fn_node(path: Path, name: str) -> ast.AST:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{path.name} has no function {name}")


def _const_keys(node: ast.Dict) -> set[str]:
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _return_dicts(path: Path, name: str) -> list[ast.Dict]:
    node = _fn_node(path, name)
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]


def _return_keys(path: Path, name: str) -> set[str]:
    keys: set[str] = set()
    for node in _return_dicts(path, name):
        keys |= _const_keys(node)
    return keys


def _return_call_names(path: Path, name: str) -> list[str]:
    """Names of functions a `return foo(...)` site calls — not literal dicts."""
    names: list[str] = []
    for node in ast.walk(_fn_node(path, name)):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if isinstance(func, ast.Name):
            names.append(func.id)
    return names


def _return_keys_following(path: Path, name: str, extra: tuple[Path, ...] = ()) -> set[str]:
    """Literal return keys, or the keys of a helper the function returns.

    UNI-2648 moved the queue dict into queue_snapshot_from_issues so the
    dashboard and the poller share one shape. `_queue_snapshot` now only
    returns that helper; a walker that stops at the wrapper sees nothing.
    """
    keys = _return_keys(path, name)
    if keys:
        return keys
    for callee in _return_call_names(path, name):
        for candidate in (path, *extra):
            try:
                keys |= _return_keys(candidate, callee)
            except AssertionError:
                continue
    return keys


def _nested_return_keys(path: Path, name: str, key: str) -> set[str]:
    keys: set[str] = set()
    for node in _return_dicts(path, name):
        for item, value in zip(node.keys, node.values):
            if isinstance(item, ast.Constant) and item.value == key and isinstance(value, ast.Dict):
                keys |= _const_keys(value)
    return keys


def _appended_dict_keys(path: Path, name: str) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(_fn_node(path, name)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "append" or not node.args or not isinstance(node.args[0], ast.Dict):
            continue
        keys |= _const_keys(node.args[0])
    return keys


def _interface_block(src: str, name: str) -> str:
    marker = f"export interface {name}"
    start = src.find(marker)
    assert start != -1, f"{TYPES.name} has no interface {name}"
    brace = src.find("{", start)
    depth = 0
    for i, ch in enumerate(src[brace:], brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[brace + 1 : i]
    raise AssertionError(f"unbalanced interface {name}")


def _interface_props(src: str, name: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for raw in _interface_block(src, name).splitlines():
        line = raw.split("//", 1)[0].strip().rstrip(";,").strip()
        match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*\??\s*:\s*(.+)$", line)
        if match:
            props[match.group(1)] = match.group(2).strip()
    return props


def _strip_ts_comments(src: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//.*?$", "", without_block, flags=re.M)


def _backend_keys() -> dict[str, set[str]]:
    return {
        "top": _return_keys(BACKEND, "mission_control_live"),
        "throughput": _nested_return_keys(BACKEND, "mission_control_live", "throughput"),
        "action": _return_keys(BACKEND, "_observability_action"),
        "session": _appended_dict_keys(SESSIONS, "active_sessions"),
        "completion": _appended_dict_keys(SESSIONS, "recent_completions"),
        "queue": _return_keys_following(
            BACKEND, "_queue_snapshot", (ELIGIBILITY,)
        ),
        "pulse": _return_keys(BACKEND, "_pulse_status"),
        "observability": _return_keys(BACKEND, "_observability_snapshot"),
    }


def _ts_keys() -> dict[str, set[str]]:
    src = TYPES.read_text(encoding="utf-8")
    return {
        "top": set(_interface_props(src, "MissionControlLive")),
        "throughput": set(_interface_props(src, "MCThroughput")),
        "action": set(_interface_props(src, "MCAction")),
        "session": set(_interface_props(src, "MCSession")),
        "completion": set(_interface_props(src, "MCCompletion")),
        "queue": set(_interface_props(src, "MCQueue")),
        "pulse": set(_interface_props(src, "MCPulse")),
        "observability": set(_interface_props(src, "MCObservability")),
    }


def test_backend_payload_keys_equal_the_ts_types_that_read_them():
    backend = _backend_keys()
    types = _ts_keys()
    assert COCKPIT_TOP <= backend["top"]
    assert COCKPIT_TOP <= types["top"]
    for section in ("throughput", "action", "session", "completion", "queue", "pulse"):
        assert backend[section] == types[section], (
            f"{section} keys drifted: backend={sorted(backend[section])} "
            f"ts={sorted(types[section])}"
        )
    assert types["observability"] <= backend["observability"]
    assert "actions" in backend["observability"] and "actions" in types["observability"]
    assert "nexus_one" in backend["top"] and "nexus_one" in types["top"]


def test_throughput_key_is_hourly_not_hourly_24h():
    backend = _backend_keys()
    types = _ts_keys()
    assert backend["throughput"] == {"hourly"}
    assert types["throughput"] == {"hourly"}
    assert "hourly_24h" not in backend["throughput"]
    assert "hourly_24h" not in types["throughput"]


def test_actions_are_typed_as_objects_not_string_arrays():
    src = TYPES.read_text(encoding="utf-8")
    actions_type = _interface_props(src, "MCObservability")["actions"]
    assert "string[]" not in actions_type
    assert "MCAction" in actions_type
    assert {"component", "next_action", "owner", "severity"} <= _ts_keys()["action"]


def test_readers_do_not_read_hourly_24h():
    for path in READERS:
        code = _strip_ts_comments(path.read_text(encoding="utf-8"))
        assert "hourly_24h" not in code, f"{path} still reads hourly_24h"


def test_proxy_fallback_emits_the_backend_hourly_key():
    route = READERS[-1].read_text(encoding="utf-8")
    code = _strip_ts_comments(route)
    assert "hourly:" in code
    assert "hourly_24h" not in code


def test_gate_detects_hourly_24h_reader():
    """Positive control: a matcher that cannot see hourly_24h is not a gate."""
    planted = "const hourly = data.throughput?.hourly_24h ?? [];\n"
    assert "hourly_24h" in _strip_ts_comments(planted)


def test_gate_detects_string_array_actions():
    planted = "export interface MCObservability {\n  actions?: string[];\n}\n"
    assert "string[]" in _interface_props(planted, "MCObservability")["actions"]


def test_interface_parser_reads_the_real_types_file():
    """Null-result guard: a broken parser would report empty==empty as a match."""
    props = _interface_props(TYPES.read_text(encoding="utf-8"), "MCThroughput")
    assert props == {"hourly": "number[]"}


def test_queue_walker_follows_the_claimable_snapshot_helper():
    """Positive control: empty keys from a wrapper-only walk is a miss, not a match."""
    expected = {"urgent", "high", "next_issue_id", "next_issue_title"}
    helper = _return_keys(ELIGIBILITY, "queue_snapshot_from_issues")
    followed = _return_keys_following(BACKEND, "_queue_snapshot", (ELIGIBILITY,))
    assert helper == expected
    assert followed == expected
    assert _backend_keys()["queue"] == expected
    # A walker that cannot see through `return queue_snapshot_from_issues(...)`
    # would report [] and then fail the live contract. Keep that miss visible.
    wrapper_only = _return_keys(BACKEND, "_queue_snapshot")
    assert wrapper_only in (set(), expected)
