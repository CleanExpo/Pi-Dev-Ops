#!/usr/bin/env python3
"""External, deterministic authorization boundary for the Senior Harness.

This module is intended for a host hook or wrapper that reports an actual
control-tool event. It does not intercept generic host tools, nor does it
interpret a model's claimed action: the exact control tool name selects a small
closed set of operations, and the scheduler remains the only authority for plan
transitions. The controller state lives outside the checkout and is
authenticated before it can be used to advance a plan.

It is a pre-execution boundary. Every call revalidates the frozen startup
checkout, so a worker's candidate mutation deliberately invalidates later calls
until a separate candidate-state/result authority binds that drift. It must not
be described as complete execution or mutation control.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[3]
for import_root in (SCRIPT_DIR, REPO_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from setup_driver import SetupError, validate_startup_receipt  # noqa: E402
from swarm.unlazy_scheduler import (  # noqa: E402
    PlanValidationError,
    begin_verification,
    guard_root_continuation,
    reserve_dispatch,
    validate_plan,
)


STATE_SCHEMA_VERSION = "1.0"
STATE_ENV_KEY = "SENIOR_HARNESS_CONTROL_HMAC_KEY"
STATE_DIR_ENV = "SENIOR_HARNESS_STATE_DIR"

# Exact names are deliberate.  Do not turn this into prefix matching: a host
# may expose an arbitrary shell or MCP tool whose label merely contains one of
# these words.
HOST_OPERATION_NAMES = {
    "senior-harness.dispatch": "dispatch",
    "senior-harness.wait": "wait",
    "senior-harness.verify": "verify",
    "senior-harness.cancel": "cancel",
    "reserve_dispatch": "dispatch",
    "begin_verification": "verify",
    "wait": "wait",
    "cancel": "cancel",
}


class ControlPlaneError(ValueError):
    """Raised when a host event cannot be admitted safely."""

    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(errors))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _state_key() -> bytes:
    key = os.environ.get(STATE_ENV_KEY, "").encode("utf-8")
    if len(key) < 32:
        raise ControlPlaneError([f"{STATE_ENV_KEY} must contain at least 32 bytes"])
    return key


def _state_mac(state: dict[str, Any], key: bytes) -> str:
    unsigned = {name: value for name, value in state.items() if name != "authority_mac"}
    return "hmac-sha256:" + hmac.new(key, _canonical(unsigned), hashlib.sha256).hexdigest()


def _state_path(value: str | Path) -> Path:
    """Keep controller state external to the project and under one trusted root."""
    root = Path(
        os.environ.get(STATE_DIR_ENV, Path.home() / ".local" / "state" / "senior-harness")
    ).expanduser().resolve()
    path = Path(value).expanduser().resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ControlPlaneError([f"control state path must be under {root}"]) from exc
    if path == root:
        raise ControlPlaneError(["control state path must name a state file, not the state directory"])
    return path


@contextlib.contextmanager
def _state_lock(path: Path):
    """Serialize a read/compare/transition/write transaction for one session."""
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - this controller is POSIX-only.
        raise ControlPlaneError(["control state locking is unavailable on this host"]) from exc
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(lock_path, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except OSError as exc:
        raise ControlPlaneError([f"control state lock failed: {exc}"]) from exc
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _read_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlPlaneError([f"control state cannot be read: {exc}"]) from exc
    if not isinstance(state, dict):
        raise ControlPlaneError(["control state must be a JSON object"])
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise ControlPlaneError(["control state schema version is invalid"])
    supplied = state.get("authority_mac")
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, _state_mac(state, _state_key())):
        raise ControlPlaneError(["control state authenticity check failed"])
    return state


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    persisted = copy.deepcopy(state)
    persisted["authority_mac"] = _state_mac(persisted, _state_key())
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(persisted, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ControlPlaneError([f"control state cannot be persisted atomically: {exc}"]) from exc


def derive_operation(event: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Derive operation only from the host-observed name and structured input."""
    if not isinstance(event, dict):
        raise ControlPlaneError(["host event must be an object"])
    name = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(name, str) or not name.strip():
        raise ControlPlaneError(["host event must include the actual tool_name"])
    if not isinstance(tool_input, dict):
        raise ControlPlaneError(["host event must include an object tool_input"])
    operation = HOST_OPERATION_NAMES.get(name.strip())
    if operation is None:
        raise ControlPlaneError([f"host tool {name!r} is not an admitted control-plane operation"])
    # A model-supplied operation label is never consulted.  If present and
    # contradictory, treating it as a forgery is safer than silently ignoring it.
    claimed = tool_input.get("operation")
    if claimed is not None and claimed != operation:
        raise ControlPlaneError(["model operation label differs from the actual host tool name"])
    return operation, tool_input


def _bound_inputs(
    startup_receipt: dict[str, Any],
    plan_raw: dict[str, Any],
    routing_request: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    if not isinstance(startup_receipt, dict) or not isinstance(plan_raw, dict) or not isinstance(routing_request, dict):
        raise ControlPlaneError(["startup receipt, plan, and routing request must be objects"])
    contract = startup_receipt.get("setup_contract")
    if not isinstance(contract, dict):
        raise ControlPlaneError(["startup receipt has no setup contract"])
    repository = contract.get("repository")
    bound_request = contract.get("routing_request")
    if not isinstance(repository, dict) or not isinstance(bound_request, dict):
        raise ControlPlaneError(["startup receipt has incomplete repository or route binding"])
    if _canonical(routing_request) != _canonical(bound_request):
        raise ControlPlaneError(["routing request differs from the startup-bound routing request"])
    try:
        validated = validate_startup_receipt(
            startup_receipt,
            literal_objective=contract.get("literal_objective"),
            project=repository.get("worktree"),
        )
        plan = validate_plan(plan_raw)
    except (SetupError, PlanValidationError) as exc:
        raise ControlPlaneError(list(exc.errors)) from exc
    if plan.task != contract.get("literal_objective"):
        raise ControlPlaneError(["plan task differs from the frozen startup objective"])
    if plan.worktree != repository.get("worktree") or plan.base_sha != repository.get("head_sha"):
        raise ControlPlaneError(["plan repository identity differs from the startup-bound checkout"])
    return validated, _digest(plan_raw)


def authorize_event(
    startup_receipt: dict[str, Any],
    plan_raw: dict[str, Any],
    routing_request: dict[str, Any],
    event: dict[str, Any],
    *,
    state_path: str | Path,
) -> dict[str, Any]:
    """Authorize one actual host control event and atomically persist its state.

    This is not a generic tool blocker. It authorizes only a host-observed
    control event. The returned plan is the authoritative next input for the
    next pre-execution invocation.
    """
    operation, tool_input = derive_operation(event)
    receipt_status, input_plan_digest = _bound_inputs(startup_receipt, plan_raw, routing_request)
    path = _state_path(state_path)
    receipt_digest = _digest(startup_receipt)
    route_digest = _digest(routing_request)
    # Atomic replacement prevents torn writes; this lock makes the full
    # read/compare/transition/write sequence a compare-and-swap transaction.
    with _state_lock(path):
        prior = _read_state(path)
        if prior is not None:
            expected = {
                "receipt_digest": receipt_digest,
                "routing_request_digest": route_digest,
                "plan_digest": input_plan_digest,
            }
            for name, value in expected.items():
                if prior.get(name) != value:
                    raise ControlPlaneError([f"control state {name} does not match the supplied bound input"])

        # This scheduler guard is also invoked for dispatch/verify/cancel/wait,
        # so forged active nodes, route swaps, or unresolved fanout are rejected
        # before a state transition is considered.
        try:
            admission = guard_root_continuation(plan_raw, routing_request, operation)
            updated_plan = copy.deepcopy(plan_raw)
            if operation == "dispatch":
                node_id = tool_input.get("node_id")
                worker_context_id = tool_input.get("worker_context_id")
                if not isinstance(node_id, str) or not isinstance(worker_context_id, str):
                    raise ControlPlaneError(["dispatch requires node_id and worker_context_id strings"])
                updated_plan = reserve_dispatch(
                    plan_raw, routing_request, node_id, worker_context_id=worker_context_id,
                )
            elif operation == "verify":
                node_id = tool_input.get("node_id")
                if not isinstance(node_id, str):
                    raise ControlPlaneError(["verify requires a node_id string"])
                updated_plan = begin_verification(plan_raw, routing_request, node_id)
            # wait and cancel are scheduler-admitted control actions. A
            # cancellation completion must arrive through a separate trusted
            # candidate/result authority; this controller never fabricates one.
        except PlanValidationError as exc:
            raise ControlPlaneError(list(exc.errors)) from exc

        output_plan_digest = _digest(updated_plan)
        state = {
            "schema_version": STATE_SCHEMA_VERSION,
            "receipt_digest": receipt_digest,
            "routing_request_digest": route_digest,
            "plan_digest": output_plan_digest,
            "last_operation": operation,
            "task_id": receipt_status["task_id"],
        }
        _write_state(path, state)
    return {
        "status": "admitted",
        "operation": operation,
        "scheduler": admission,
        "plan": updated_plan,
        "state_path": str(path),
    }


def _read_json(path: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlPlaneError([f"cannot read JSON input {path}: {exc}"]) from exc
    if not isinstance(payload, dict):
        raise ControlPlaneError([f"JSON input {path} must be an object"])
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    authorize = command.add_parser("authorize", help="authorize one host-observed control event")
    authorize.add_argument("--receipt", required=True)
    authorize.add_argument("--plan", required=True)
    authorize.add_argument("--routing-request", required=True)
    authorize.add_argument("--event", required=True)
    authorize.add_argument("--state", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = authorize_event(
            _read_json(args.receipt), _read_json(args.plan), _read_json(args.routing_request), _read_json(args.event),
            state_path=args.state,
        )
    except ControlPlaneError as exc:
        print(json.dumps({"status": "denied", "errors": list(exc.errors)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
