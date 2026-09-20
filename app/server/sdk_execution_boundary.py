"""Read-only admission and required isolation options for subscription SDK runs."""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from . import config, tool_gate

class ExecutionBoundaryError(RuntimeError):
    """The host cannot supply the required autonomous execution boundary."""


_RUNTIME_ENV = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
    "TMPDIR", "TMP", "TEMP", "SYSTEMROOT", "WINDIR", "PATHEXT",
})


def _child_environment() -> dict[str, str]:
    """Override SDK inheritance without mutating the concurrent server's env.

    The SDK merges env with os.environ, so a mere allowlist dict is insufficient.
    Blank every other inherited value, including unknown application credentials
    and interpreter preload flags. CLI auth must use its separately verified
    credential store; no bearer token or API key is supplied in this environment.
    """
    from .provider_policy import CLAUDE_ROUTING_ENV
    child = {name: value if name.upper() in _RUNTIME_ENV else "" for name, value in os.environ.items()}
    # SDK overlays rather than replaces os.environ. Pin these even when absent
    # now, so a later parent-env update cannot redirect auth or API transport.
    for name in (*CLAUDE_ROUTING_ENV, "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR"):
        child[name] = ""
    # CLAUDE_CONFIG_DIR is a PATH, not a credential, so blanking it is not the
    # same as unsetting it: on Linux an empty value resolves the CLI's credential
    # store to the wrong location, and a correctly logged-in subscription host then
    # reports loggedIn:false and is refused by provider_policy's transport check.
    # Pin the explicit default instead. The key stays present in the returned
    # mapping, so the SDK overlay still cannot fall back to a parent's redirected
    # value, and a degenerate HOME stays blank as claude_json_path also requires.
    #
    # Linux only, and that is measured rather than cautious. On darwin the live
    # credential is in the keychain and setting this variable at all switches the
    # CLI to its file store, where a stale ~/.claude/.credentials.json authenticates
    # as nobody - so pinning breaks the supported darwin path that blanking leaves
    # working. Deployment is Linux; darwin keeps today's behaviour.
    home = child.get("HOME", "").strip()
    if sys.platform == "linux" and home and home != "/":
        child["CLAUDE_CONFIG_DIR"] = str(Path(home) / ".claude")
    return child


def _require_supported_cli(path: str, env: dict[str, str]) -> None:
    """Reject older CLIs which can silently ignore the required sandbox keys.

    v2.1.260 is the documented baseline reviewed for this policy, not a request
    to install or upgrade it. See code.claude.com/docs/en/sandboxing.
    """
    try:
        identity = _cli_identity(path)
        result = subprocess.run([path, "--version"], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10, check=False,
                                creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                               | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)))
        match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", result.stdout)
        if (result.returncode == 0 and match
                and tuple(map(int, match.groups())) >= (2, 1, 260)
                and _cli_identity(path) == identity):
            return
    except (OSError, subprocess.SubprocessError):
        pass
    raise ExecutionBoundaryError("execution_blocked: supported sandbox CLI version could not be verified")


def _execution_cli() -> str:
    """Check local host prerequisites without launching processes or reading auth."""
    if sys.platform not in {"linux", "darwin"}:
        raise ExecutionBoundaryError("execution_blocked: sandbox unsupported on this platform")
    if sys.platform == "linux" and any(shutil.which(name) is None for name in ("bwrap", "socat")):
        raise ExecutionBoundaryError("execution_blocked: required sandbox dependencies are unavailable")
    cli = shutil.which("claude")
    if cli is None:
        raise ExecutionBoundaryError("execution_blocked: sandbox CLI is unavailable")
    return str(Path(cli).resolve())


def generation_readiness() -> dict:
    """Static admission facts only; dispatch still verifies auth and isolation."""
    from .provider_policy import ProviderPolicyError, check_claude_configuration
    blockers = []
    for check in (check_claude_configuration, _execution_cli):
        try:
            check()
        except (ProviderPolicyError, ExecutionBoundaryError) as exc:
            blockers.append(str(exc))
    return {
        "transport": "anthropic_agent_sdk",
        "status": "blocked" if blockers else "unverified",
        "ready": False if blockers else None,
        "blockers": blockers,
        "auth_verified": False, "cost_verified": False,
    }


def _cli_identity(path: str) -> tuple[int, int, int, int]:
    """Detect replacement during preflight without reading the executable body."""
    try:
        stat = Path(path).stat()
    except OSError:
        raise ExecutionBoundaryError("execution_blocked: verified CLI is unavailable") from None
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _execution_options(workspace: str, *, cli_resolver=_execution_cli, version_check=_require_supported_cli, gate_factory=None, pretool_factory=None) -> dict:
    """Require sandboxed commands and workspace hooks before any model request.

    Native Windows is unsupported. The CLI must also fail closed if namespace
    or Seatbelt setup fails at runtime; this preflight is not a VM boundary.
    """
    from .provider_policy import check_claude_configuration
    check_claude_configuration()
    cli = cli_resolver()
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise ExecutionBoundaryError("execution_blocked: workspace does not exist")
    env = _child_environment()
    version_check(cli, env)
    return _sandbox_options(root, cli, env, gate_factory, pretool_factory)


def _sandbox_options(root, cli, env, gate_factory, pretool_factory):
    from claude_agent_sdk.types import HookMatcher  # noqa: PLC0415
    private = [str(root / pattern) for pattern in (
        "**/.env*", "**/*.pem", "**/*.key", ".git", ".claude",
        "**/.session-secret", "**/.password-hash",
    )]
    # The server's live state is a sibling of generated workspaces in deployment,
    # not necessarily under HOME or the workspace-relative secret patterns.
    private.append(str(Path(config.DATA_DIR).resolve()))
    return {
        "cli_path": cli, "env": env,
        "permission_mode": "default", "setting_sources": [],
        "tools": sorted(tool_gate.WORKSPACE_TOOLS), "allowed_tools": [],
        "mcp_servers": {}, "strict_mcp_config": True,
        "can_use_tool": gate_factory(str(root)),
        "hooks": {"PreToolUse": [HookMatcher(hooks=[pretool_factory(str(root))])]},
        "settings": json.dumps({"permissions": {"blockReadsOutsideWorkingDirectories": True}}),
        "sandbox": {
            "enabled": True, "failIfUnavailable": True,
            "autoAllowBashIfSandboxed": False, "allowUnsandboxedCommands": False,
            "excludedCommands": [], "enableWeakerNestedSandbox": False,
            "filesystem": {"disabled": False,
                           "denyRead": [str(Path.home()), "/proc", "/run/secrets", *private],
                           "allowRead": [str(root)], "denyWrite": private},
            "network": {"allowedDomains": [], "allowUnixSockets": [],
                        "allowAllUnixSockets": False, "allowLocalBinding": False},
            "credentials": {"envVars": [{"name": name, "mode": "deny"}
                                         for name in os.environ if name.upper() not in _RUNTIME_ENV]},
        },
    }
