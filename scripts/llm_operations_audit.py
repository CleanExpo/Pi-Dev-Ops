#!/usr/bin/env python3
"""Bounded offline LLM operations inventory. Never prints source/config contents.

Python 3.11+, standard library only. Inputs are read-only; only --output is written.
No model calls, login probes, runner starts, config changes, or network requests.
Optional subprocesses run only installed Claude/Codex --version with bounded output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import time
import tomllib
from typing import Any

MAX_BYTES = 512 * 1024
MAX_ENTRIES = 12_000
MAX_DEPTH = 12
SECRET = re.compile(r"(?i)(?:sk-[a-z0-9_-]+|lin_api_[a-z0-9_-]+|Bearer\s+\S+|(?:postgres|postgresql)://\S+)")
MODEL = re.compile(r"(?:gpt-[0-9][a-z0-9.-]{0,63}|o[1-9](?:-[a-z0-9.-]+)?|claude-(?:opus|sonnet|haiku|fable)-[0-9][a-z0-9.-]{0,63}|opus|sonnet|haiku|opusplan)\Z")
SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,100}\Z")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "sessions", "memories", "attachments", "logs", "auth"}
DENY_FILES = {"auth.json", "credentials.json", "credentials", "session.json", ".credentials.json"}
VERIFIED_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna"}
CURRENT_CLI_ALIASES = {"opus", "sonnet", "haiku", "opusplan"}
DEFAULT_ROUTE_FILES = (
    "app/server/model_registry.py", "app/server/model_policy.py",
    "app/server/provider_router.py", "swarm/model_router.py",
    "scripts/codex-review.sh", "scripts/fallback_dryrun.py",
    "skills/pi-dev-ops-model-farm/scripts/model-farm.py",
)


def safe_text(value: str) -> str:
    """Paths/identifiers only; arbitrary source text must never call this for output."""
    return SECRET.sub("[redacted]", value).replace("\n", "[newline]").replace("\r", "[newline]")


def allowed(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
        return any(resolved.is_relative_to(root) for root in roots)
    except (OSError, RuntimeError):
        return False


def denied(path: Path) -> bool:
    return any(part in SKIP_DIRS or ".env" in part for part in path.parts) or path.name in DENY_FILES or bool(SECRET.search(str(path)))


def read_bounded(path: Path, roots: list[Path]) -> tuple[str | None, str]:
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return None, "excluded_path"
    if denied(path) or denied(resolved) or not any(resolved.is_relative_to(root) for root in roots):
        return None, "excluded_path"
    try:
        # Avoid special files, FIFOs and accidental large reads.
        if not resolved.is_file():
            return None, "missing"
        if resolved.stat().st_size > MAX_BYTES:
            return None, "over_byte_limit"
        with resolved.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return None, "over_byte_limit"
        return data.decode("utf-8"), "ok"
    except UnicodeDecodeError:
        return None, "invalid_utf8"
    except (OSError, RuntimeError):
        return None, "unreadable"


def file_identity(path: Path, text: str) -> dict[str, Any]:
    return {"path": safe_text(str(path.absolute())), "source_path": safe_text(str(path.resolve())),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "bytes": len(text.encode("utf-8")), "characters": len(text),
            "lines": len(text.splitlines()), "estimated_tokens_chars_div_4": math.ceil(len(text) / 4)}


def instructions(home: Path, projects: list[Path], roots: list[Path]) -> list[dict[str, Any]]:
    paths = [home / ".codex/AGENTS.md", home / ".claude/CLAUDE.md", home / "CLAUDE.md"]
    paths += [project / filename for project in projects for filename in ("AGENTS.md", "CLAUDE.md")]
    rows = []
    queue = [(path, None) for path in dict.fromkeys(paths)]
    seen: set[Path] = set()
    while queue and len(rows) < 64:
        path, imported_by = queue.pop(0)
        if path.absolute() in seen:
            continue
        seen.add(path.absolute())
        text, status = read_bounded(path, roots)
        row = {**(file_identity(path, text) if text is not None else {"path": safe_text(str(path))}), "status": status}
        if imported_by:
            row["imported_by"] = safe_text(str(imported_by))
        rows.append(row)
        if text is not None:
            for reference in re.findall(r"^@([^\s]+)\s*$", text, re.MULTILINE)[:8]:
                target = home / reference[2:] if reference.startswith("~/") else path.parent / reference
                queue.append((target, path))
    return rows


def frontmatter(text: str) -> tuple[str | None, int, str]:
    """Read only name/description metadata; deliberately not a general YAML parser."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, 0, "missing_frontmatter"
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        return None, 0, "malformed_frontmatter"
    name = None
    description = ""
    collecting = False
    for line in lines[1:end]:
        if line.startswith("name:"):
            candidate = line[5:].strip().strip("\"'")
            if SAFE_NAME.fullmatch(candidate) and not SECRET.search(candidate):
                name = candidate
        if line.startswith("description:"):
            description = line[len("description:"):].strip()
            collecting = description in {">", "|", ">-", "|-"}
            if collecting:
                description = ""
        elif collecting and line.startswith((" ", "\t")):
            description += " " + line.strip()
        elif collecting:
            collecting = False
    return name, len(description), "ok" if name and description else "missing_or_invalid_metadata"


def skill_catalog(skill_roots: list[Path], roots: list[Path], max_entries: int = MAX_ENTRIES) -> dict[str, Any]:
    rows, issues, duplicates = [], [], []
    seen_dirs: set[Path] = set()
    sources: dict[Path, str] = {}
    entries = 0
    stack = [(root, 0) for root in reversed(skill_roots)]
    limited = False
    while stack:
        directory, depth = stack.pop()
        if entries >= max_entries:
            limited = True
            break
        actual = directory.resolve()
        if denied(directory) or denied(actual) or not any(actual.is_relative_to(root) for root in roots):
            issues.append({"path": safe_text(str(directory)), "status": "excluded_path"})
            continue
        skill = directory / "SKILL.md"
        text, status = read_bounded(skill, roots)
        if text is not None:
            name, description_chars, metadata_status = frontmatter(text)
            row = {**file_identity(skill, text), "name": name, "description_characters": description_chars,
                   "metadata_status": metadata_status}
            source = skill.resolve()
            if source in sources:
                duplicates.append({"alias_path": row["path"], "source_path": row["source_path"], "first_path": sources[source]})
            else:
                sources[source] = row["path"]
                rows.append(row)
            # Only local SKILL.md references; never render arbitrary Markdown text.
            refs = re.findall(r"(?:\]\(([^)\s]*SKILL\.md)\)|`([^`\s]*SKILL\.md)`)", text)
            for pair in refs[:100]:
                ref = next(part for part in pair if part)
                if "://" in ref or ref.startswith("skill:"):
                    continue
                target = directory / ref
                if denied(target) or denied(target.resolve()) or not allowed(target, roots):
                    issues.append({"path": row["path"], "status": "excluded_skill_reference"})
                elif not target.is_file():
                    # Inline code paths can mean repository-root references.
                    root_relative_exists = not pair[0] and any((root / ref).is_file() and allowed(root / ref, roots) and not denied(root / ref) and not denied((root / ref).resolve()) for root in roots)
                    if not root_relative_exists:
                        issues.append({"path": row["path"], "target_path": safe_text(str(target.absolute())),
                                       "status": "broken_skill_reference" if pair[0] else "unresolved_skill_reference"})
        elif status not in {"missing"}:
            issues.append({"path": safe_text(str(skill)), "status": status})
        if actual in seen_dirs:
            continue
        seen_dirs.add(actual)
        if depth >= MAX_DEPTH:
            limited = True
            continue
        try:
            with os.scandir(directory) as children:
                for child in children:
                    entries += 1
                    if entries >= max_entries:
                        limited = True
                        break
                    if child.name not in SKIP_DIRS and child.is_dir(follow_symlinks=True):
                        stack.append((Path(child.path), depth + 1))
        except OSError:
            issues.append({"path": safe_text(str(directory)), "status": "unreadable_directory"})
    return {"unique_skills": len(rows), "duplicate_aliases": duplicates, "skills": rows, "issues": issues,
            "entries_examined": entries, "truncated": limited,
            "rough_catalog_characters": sum(len(row["name"] or "") + row["description_characters"] for row in rows),
            "budget_note": "Name + description characters only; tool schemas, platform prefixes and actual loaded skills are unknown."}


def model_value(value: Any) -> str | None:
    return value if isinstance(value, str) and MODEL.fullmatch(value) and not SECRET.search(value) else None


def model_configs(home: Path, projects: list[Path], roots: list[Path]) -> list[dict[str, Any]]:
    candidates = [home / ".codex/config.toml", home / ".claude/settings.json"]
    candidates += [project / ".codex/config.toml" for project in projects]
    candidates += [project / ".claude/settings.json" for project in projects]
    rows = []
    for path in candidates:
        text, status = read_bounded(path, roots)
        row: dict[str, Any] = {"path": safe_text(str(path)), "status": status, "allowed_values": {}}
        if text is not None:
            try:
                config = tomllib.loads(text) if path.suffix == ".toml" else json.loads(text)
                if not isinstance(config, dict):
                    raise ValueError
                fields: dict[str, Any] = {"model": config.get("model")}
                if path.suffix == ".toml":
                    fields["model_reasoning_effort"] = config.get("model_reasoning_effort")
                elif isinstance(config.get("env"), dict):
                    for key in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL"):
                        fields[key] = config["env"].get(key)
                for key, value in fields.items():
                    clean = value if key == "model_reasoning_effort" and value in ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra") else model_value(value)
                    if clean is not None:
                        row["allowed_values"][key] = clean
                row["status"] = "ok"
            except (ValueError, tomllib.TOMLDecodeError):
                row["status"] = "malformed_config"
        rows.append(row)
    return rows


def source_routes(projects: list[Path], roots: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for project in projects:
        for relative in DEFAULT_ROUTE_FILES:
            path = project / relative
            text, status = read_bounded(path, roots)
            if text is None:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                for candidate in re.findall(r"[\"']((?:claude-|gpt-|o[1-9])[a-z0-9.-]+)[\"']", line):
                    clean = model_value(candidate)
                    if clean:
                        rows.append({"path": safe_text(str(path)), "line": number, "model": clean,
                                     "evidence": "source_literal_only", "availability": "unknown",
                                     "catalog_status": "listed_current" if clean in VERIFIED_MODELS else "verify_identifier_or_legacy_route",
                                     "review": "verify_against_provider_catalog_and_account"})
    return rows


def bounded_version(executable: str, timeout: float = 4.0, output_limit: int = 4096) -> dict[str, Any]:
    """Only versions escape; capped pipe reads and deadline prevent probe hangs."""
    started = time.monotonic()
    process = None
    selector = selectors.DefaultSelector()
    data = bytearray()
    status = "ok"
    try:
        process = subprocess.Popen([executable, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        assert process.stdout is not None
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                status = "timeout"
                break
            for key, _ in selector.select(min(remaining, 0.1)):
                chunk = os.read(key.fd, min(1024, output_limit + 1 - len(data)))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                data.extend(chunk)
                if len(data) > output_limit:
                    status = "output_limit"
                    break
            if status != "ok":
                break
        if status == "ok":
            try:
                process.wait(timeout=max(0.001, timeout - (time.monotonic() - started)))
                if process.returncode:
                    status = "failed"
            except subprocess.TimeoutExpired:
                status = "timeout"
        version = re.search(rb"(?<![0-9])([0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4})(?![0-9])", data)
        return {"status": status, "version": version.group(1).decode() if status == "ok" and version else None}
    except OSError:
        return {"status": "unavailable", "version": None}
    finally:
        selector.close()
        if process is not None:
            if process.poll() is None or status != "ok":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
            if process.stdout:
                process.stdout.close()


def cli_versions(timeout: float, enabled: bool) -> list[dict[str, Any]]:
    rows = []
    for name in ("claude", "codex"):
        executable = shutil.which(name)
        result = bounded_version(executable, timeout) if enabled and executable else {"status": "not_probed" if executable else "not_found", "version": None}
        rows.append({"cli": name, **result, "account_access": "unknown", "selected_runtime_model": "unknown"})
    return rows


def pid_state(pid: Any) -> str:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
        return "unknown"
    try:
        os.kill(pid, 0)
        return "present_identity_unverified"
    except ProcessLookupError:
        return "absent"
    except (PermissionError, OSError):
        return "unknown"


def runner_receipts(runner_roots: list[Path], roots: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for directory in runner_roots:
        for filename in ("state.json", "status.json", "runner-state.json"):
            path = directory / filename
            text, status = read_bounded(path, roots)
            row: dict[str, Any] = {"path": safe_text(str(path)), "status": status, "runtime": "unknown"}
            if text is not None:
                try:
                    data = json.loads(text)
                    if not isinstance(data, dict):
                        raise ValueError
                    recorded = data.get("state", data.get("status"))
                    recorded = recorded if recorded in ("running", "stopped", "idle", "paused", "busy", "ready", "failed") else "unknown"
                    process = pid_state(data.get("pid"))
                    row.update(recorded_state=recorded, process=process, evidence="local_receipt_only")
                    if recorded in ("running", "busy", "ready") and process == "absent":
                        row["runtime"] = "recorded_active_but_pid_absent"
                    elif recorded in ("stopped", "paused"):
                        row["runtime"] = "recorded_stopped_process_unverified" if process != "absent" else "recorded_stopped_pid_absent"
                    # A live/reused PID never establishes runner health or identity.
                    row["age_seconds"] = round(max(0, time.time() - path.stat().st_mtime), 1)
                except (ValueError, OSError):
                    row["status"] = "malformed_receipt"
            rows.append(row)
    return rows


def audit(home: Path, projects: list[Path], skill_roots: list[Path] | None = None,
          runner_roots: list[Path] | None = None, probe_clis: bool = True,
          timeout: float = 4.0, max_entries: int = MAX_ENTRIES) -> dict[str, Any]:
    home = home.resolve()
    projects = [path.resolve() for path in projects]
    skills = skill_roots if skill_roots is not None else [home / ".agents/skills", home / ".codex/skills"] + [project / folder for project in projects for folder in ("skills", ".agents/skills", ".claude/skills")]
    runners = runner_roots or []
    roots = list(dict.fromkeys([home, (home / ".codex").resolve(), (home / ".claude").resolve(), *projects, *[path.resolve() for path in skills], *[path.resolve() for path in runners]]))
    return {"schema_version": 1, "vendor_catalog_as_of": "2026-10-10",
            "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "mode": "offline_read_only_inventory",
            "scope": {"home_root": safe_text(str(home)), "project_roots": [safe_text(str(p)) for p in projects]},
            "bounds": {"max_file_bytes": MAX_BYTES, "max_catalog_entries": max_entries, "max_catalog_depth": MAX_DEPTH, "cli_timeout_seconds": timeout},
            "instructions": instructions(home, projects, roots), "skill_catalog": skill_catalog(skills, roots, max_entries),
            "model_configs": model_configs(home, projects, roots), "source_routes": source_routes(projects, roots),
            "cli_versions": cli_versions(timeout, probe_clis), "runner_receipts": runner_receipts(runners, roots),
            "limits": ["Character/4 estimates are not tokenizer measurements or actual loaded context.",
                       "Source model literals are not proof of selected or available runtime models.",
                       "No env/auth/session data, provider API, paid evaluation, account, tmux or process-command inspection.",
                       "Runner receipts and PID existence cannot prove process identity or health.",
                       "Instruction scope is named entrypoints and up to 64 import rows; auto-loaded rules, ancestors and nested conditional instructions require separate native context inspection.",
                       "Plugin roots and runner receipts require explicit relevant roots; catalog can be partial."]}


def write_report(output: Path, report: dict[str, Any], inputs: list[Path], external_root: Path) -> None:
    resolved = output.resolve()
    if not external_root.is_dir() or not resolved.is_relative_to(external_root.resolve()):
        raise ValueError("output must be on the mounted external storage root")
    if denied(output) or denied(resolved) or output.suffix != ".json" or output.exists():
        raise ValueError("output must be a new, non-sensitive JSON receipt")
    if any(resolved == item.resolve() for item in inputs):
        raise ValueError("output cannot replace an input")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting a concurrent receipt or a symlink.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, action="append", default=[])
    parser.add_argument("--skill-root", type=Path, action="append")
    parser.add_argument("--runner-root", type=Path, action="append", default=[])
    parser.add_argument("--no-cli-probes", action="store_true")
    parser.add_argument("--cli-timeout", type=float, default=4)
    parser.add_argument("--max-entries", type=int, default=MAX_ENTRIES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 0.1 <= args.cli_timeout <= 10 or not 1 <= args.max_entries <= MAX_ENTRIES:
        parser.error("bounds must be 0.1–10 seconds and 1–12000 entries")
    if not args.home_root.is_dir() or any(not root.is_dir() for root in args.project_root):
        parser.error("home and project roots must be existing directories")
    try:
        report = audit(args.home_root, args.project_root, args.skill_root, args.runner_root, not args.no_cli_probes, args.cli_timeout, args.max_entries)
        write_report(args.output, report, [args.home_root, *args.project_root, *(args.skill_root or []), *args.runner_root], Path("/Volumes/Storage Unit"))
    except (ValueError, OSError):
        parser.exit(2, "audit failed: invalid output path, unavailable storage or write failure\n")
    print(f"wrote offline inventory: {safe_text(str(args.output))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
