"""Repo-intake audit artifacts for Pi-Dev-Ops.

External repositories and docs must leave a written intake receipt before any
implementation lane starts. This module is deterministic and local-only: it does
not clone, fetch, vendor, or mutate source repositories.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_TEXT_LIMIT = 1200
_MANIFEST_NAMES = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "Dockerfile",
    "docker-compose.yml",
    "pnpm-lock.yaml",
    "uv.lock",
)

from tao.build_router import classify_intent

_URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)


def extract_source_url(command: str) -> str | None:
    """Return the first URL from a founder command, trimmed of prose punctuation."""
    match = _URL_RE.search(command)
    if not match:
        return None
    return match.group(0).rstrip(".,;:")


def slug_for_source(source_url: str | None, command: str) -> str:
    """Create a stable, filesystem-safe slug for an intake artifact."""
    basis = source_url or command
    cleaned = re.sub(r"^https?://", "", basis.lower())
    cleaned = cleaned.replace(".git", "")
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:8]
    prefix = cleaned[:64].strip("-") or "repo-intake"
    return f"{prefix}-{digest}"


def build_repo_intake_audit(command: str, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """Build a repo-intake audit payload without touching the network."""
    source_url = extract_source_url(command)
    route = classify_intent(command)
    timestamp = (now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0).isoformat()
    is_repo_intake = route == "repo-intake"
    return {
        "schema_version": 1,
        "created_at": timestamp,
        "command": command,
        "source_url": source_url,
        "route": route,
        "status": "intake-required" if is_repo_intake else "not-repo-intake",
        "no_build_started": True,
        "fit_classification": "pending-read-only-scan" if is_repo_intake else "not-applicable",
        "detected_stack": [],
        "license": "unknown",
        "manifests": [],
        "ci_commands": [],
        "capability_claims": _extract_capability_claims(command),
        "integration_risks": [
            "Do not vendor, fork, or implement until read-only scan is complete.",
            "Verify license, maintenance activity, security posture, and overlap with existing Pi-Dev-Ops components.",
        ] if is_repo_intake else [],
        "recommended_next_lane": "repo-intake-read-only-scan" if is_repo_intake else route,
        "verification": {
            "artifact_only": True,
            "network_calls": 0,
            "repository_mutations": 0,
            "next_required_evidence": [
                "README/docs summary",
                "manifest/package map",
                "license finding",
                "CI/test commands",
                "fit classification: reference-only/tool-adoption/fork-and-adapt/vendor-risk/not-fit",
            ] if is_repo_intake else [],
        },
    }


def write_repo_intake_audit(command: str, audits_dir: str | Path, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """Write JSON + Markdown repo-intake receipts and return artifact paths."""
    audit = build_repo_intake_audit(command, now=now)
    source_url = audit.get("source_url")
    slug = slug_for_source(source_url, command)
    target_dir = Path(audits_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / f"{slug}.json"
    md_path = target_dir / f"{slug}.md"
    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_repo_intake_markdown(audit), encoding="utf-8")
    return {
        "audit": audit,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }


def clone_repo_to_sandbox(source_url: str, sandbox_root: str | Path, *, force: bool = False) -> dict[str, Any]:
    """Shallow-clone an external repo into a controlled sandbox directory.

    This performs the only network step in repo-intake and still does not build,
    vendor, install dependencies, or mutate the cloned repository after checkout.
    Existing target directories are refused unless force=True.
    """
    if not source_url or not source_url.startswith(("http://", "https://")):
        raise ValueError("source_url must be an http(s) URL")
    root = Path(sandbox_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / slug_for_source(source_url, source_url)
    if target.exists():
        if not force:
            raise FileExistsError(f"sandbox target already exists: {target}")
        shutil.rmtree(target)
    cmd = ["git", "clone", "--depth", "1", "--filter=blob:none", source_url, str(target)]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
    return {
        "source_url": source_url,
        "sandbox_path": str(target),
        "clone_command": "git clone --depth 1 --filter=blob:none <source_url> <sandbox_path>",
        "network_calls": 1,
        "repository_mutations": 0,
        "build_started": False,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def scan_local_repo(repo_path: str | Path) -> dict[str, Any]:
    """Read-only scan of a local sandbox clone/path for repo-intake evidence."""
    root = Path(repo_path)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"repo path not found: {root}")

    manifests = _find_manifest_files(root)
    readme = _read_first_existing(root, ["README.md", "readme.md", "Readme.md"])
    license_text = _read_first_existing(root, ["LICENSE", "LICENSE.md", "LICENCE", "LICENCE.md"])
    ci_commands = _detect_ci_commands(root)
    detected_stack = _detect_stack(root, manifests)
    license_name = _classify_license(license_text)
    risk_flags = _scan_risks(root, license_name)
    fit = _classify_fit(detected_stack, license_name, risk_flags)

    return {
        "scanned_path": str(root),
        "detected_stack": detected_stack,
        "license": license_name,
        "manifests": manifests,
        "ci_commands": ci_commands,
        "readme_summary": readme[:_TEXT_LIMIT] if readme else "",
        "risk_flags": risk_flags,
        "fit_classification": fit,
        "scan_mode": "read-only-local-path",
        "network_calls": 0,
        "repository_mutations": 0,
    }


def apply_repo_scan(audit: dict[str, Any], scan: dict[str, Any], clone: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge read-only scan evidence into an existing repo-intake audit."""
    updated = dict(audit)
    updated["detected_stack"] = scan.get("detected_stack", [])
    updated["license"] = scan.get("license", "unknown")
    updated["manifests"] = scan.get("manifests", [])
    updated["ci_commands"] = scan.get("ci_commands", [])
    updated["readme_summary"] = scan.get("readme_summary", "")
    updated["risk_flags"] = scan.get("risk_flags", [])
    updated["fit_classification"] = scan.get("fit_classification", "pending-read-only-scan")
    updated["recommended_next_lane"] = _next_lane_after_scan(updated["fit_classification"])
    if clone:
        updated["sandbox_clone"] = {
            "sandbox_path": clone.get("sandbox_path"),
            "clone_command": clone.get("clone_command"),
            "build_started": clone.get("build_started", False),
        }
    verification = dict(updated.get("verification", {}))
    verification["artifact_only"] = False
    verification["read_only_scan"] = True
    verification["network_calls"] = scan.get("network_calls", 0) + (clone or {}).get("network_calls", 0)
    verification["repository_mutations"] = scan.get("repository_mutations", 0) + (clone or {}).get("repository_mutations", 0)
    verification["build_started"] = False
    updated["verification"] = verification
    return updated


def write_repo_intake_scan(
    command: str,
    audits_dir: str | Path,
    repo_path: str | Path,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Write JSON + Markdown repo-intake receipts with local scan evidence."""
    audit = build_repo_intake_audit(command, now=now)
    audit = apply_repo_scan(audit, scan_local_repo(repo_path))
    source_url = audit.get("source_url")
    slug = slug_for_source(source_url, command)
    target_dir = Path(audits_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / f"{slug}.json"
    md_path = target_dir / f"{slug}.md"
    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_repo_intake_markdown(audit), encoding="utf-8")
    return {"audit": audit, "json_path": str(json_path), "markdown_path": str(md_path)}


def write_repo_intake_clone_scan(
    command: str,
    audits_dir: str | Path,
    sandbox_root: str | Path,
    *,
    now: dt.datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Sandbox-clone repo URL, read-only scan it, and write enriched receipts."""
    audit = build_repo_intake_audit(command, now=now)
    source_url = audit.get("source_url")
    if not source_url:
        raise ValueError("repo-intake clone requires a source URL in the command")
    clone = clone_repo_to_sandbox(str(source_url), sandbox_root, force=force)
    audit = apply_repo_scan(audit, scan_local_repo(clone["sandbox_path"]), clone=clone)
    slug = slug_for_source(source_url, command)
    target_dir = Path(audits_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    json_path = target_dir / f"{slug}.json"
    md_path = target_dir / f"{slug}.md"
    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_repo_intake_markdown(audit), encoding="utf-8")
    return {"audit": audit, "clone": clone, "json_path": str(json_path), "markdown_path": str(md_path)}


def format_repo_intake_markdown(audit: dict[str, Any]) -> str:
    """Render a human-readable repo-intake receipt."""
    claims = audit.get("capability_claims") or ["none captured from command"]
    risks = audit.get("integration_risks") or ["none"]
    next_evidence = audit.get("verification", {}).get("next_required_evidence") or ["none"]
    stack = audit.get("detected_stack") or ["unknown"]
    manifests = audit.get("manifests") or ["none"]
    ci_commands = audit.get("ci_commands") or ["none"]
    risks_scan = audit.get("risk_flags") or ["none"]
    readme_summary = audit.get("readme_summary") or "not scanned yet"
    sandbox_clone = audit.get("sandbox_clone") or {}
    return "\n".join([
        "# Repo Intake Audit",
        "",
        f"- Created: {audit.get('created_at')}",
        f"- Source URL: {audit.get('source_url') or 'none detected'}",
        f"- Route: {audit.get('route')}",
        f"- Status: {audit.get('status')}",
        f"- No build started: {audit.get('no_build_started')}",
        f"- Fit classification: {audit.get('fit_classification')}",
        f"- Recommended next lane: {audit.get('recommended_next_lane')}",
        "",
        "## Founder command",
        "",
        audit.get("command", ""),
        "",
        "## Captured capability claims",
        "",
        *[f"- {claim}" for claim in claims],
        "",
        "## Initial integration risks",
        "",
        *[f"- {risk}" for risk in risks],
        "",
        "## Read-only scan evidence",
        "",
        f"- Sandbox path: {sandbox_clone.get('sandbox_path', 'not cloned by this artifact')}",
        f"- Clone command: {sandbox_clone.get('clone_command', 'not cloned by this artifact')}",
        f"- Build started: {sandbox_clone.get('build_started', False)}",
        f"- License: {audit.get('license', 'unknown')}",
        "- Detected stack:",
        *[f"  - {item}" for item in stack],
        "- Manifests:",
        *[f"  - {item}" for item in manifests],
        "- CI/test commands:",
        *[f"  - {item}" for item in ci_commands],
        "- Scan risk flags:",
        *[f"  - {item}" for item in risks_scan],
        "",
        "## README/docs summary",
        "",
        readme_summary,
        "",
        "## Next required evidence before build",
        "",
        *[f"- {item}" for item in next_evidence],
        "",
    ])


def _extract_capability_claims(command: str) -> list[str]:
    """Extract lightweight capability claims from command prose."""
    claims: list[str] = []
    patterns = [
        r"\b\d+\+?\s+[a-zA-Z][a-zA-Z0-9_-]+",
        r"\b(?:built-in|providers?|tools?|lsp|dap|rust|python|typescript|docker|ci)\b[^,. ;]*",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, command, flags=re.IGNORECASE):
            value = match.group(0).strip()
            if value and value.lower() not in {claim.lower() for claim in claims}:
                claims.append(value)
    return claims[:12]


def _find_manifest_files(root: Path) -> list[str]:
    found: list[str] = []
    for name in _MANIFEST_NAMES:
        path = root / name
        if path.exists():
            found.append(name)
    workflows = root / ".github" / "workflows"
    if workflows.exists():
        for path in sorted(workflows.glob("*.y*ml"))[:12]:
            found.append(str(path.relative_to(root)).replace("\\", "/"))
    return found


def _read_first_existing(root: Path, names: list[str]) -> str:
    for name in names:
        path = root / name
        if path.exists() and path.is_file():
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return ""
    return ""


def _detect_ci_commands(root: Path) -> list[str]:
    haystacks: list[str] = []
    workflows = root / ".github" / "workflows"
    if workflows.exists():
        for path in sorted(workflows.glob("*.y*ml"))[:12]:
            try:
                haystacks.append(path.read_text(encoding="utf-8", errors="replace").lower())
            except OSError:
                continue
    package = root / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text(encoding="utf-8", errors="replace"))
            scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
            for name, value in scripts.items():
                if any(token in name.lower() for token in ("test", "lint", "type", "build")):
                    haystacks.append(str(value).lower())
        except (OSError, json.JSONDecodeError):
            pass
    candidates = [
        "pytest",
        "python -m pytest",
        "npm test",
        "npm run test",
        "pnpm test",
        "pnpm lint",
        "pnpm type-check",
        "yarn test",
        "cargo test",
        "go test",
        "ruff",
        "mypy",
        "vitest",
        "jest",
    ]
    detected: list[str] = []
    text = "\n".join(haystacks)
    for candidate in candidates:
        if candidate in text and candidate not in detected:
            detected.append(candidate)
    return detected


def _detect_stack(root: Path, manifests: list[str]) -> list[str]:
    stack: list[str] = []
    manifest_text = " ".join(manifests).lower()
    checks = [
        ("python", ["pyproject.toml", "requirements.txt", "setup.py"]),
        ("typescript/javascript", ["package.json", "pnpm-lock.yaml", "yarn.lock"]),
        ("rust", ["cargo.toml"]),
        ("go", ["go.mod"]),
        ("docker", ["dockerfile", "docker-compose.yml"]),
        ("github-actions", [".github/workflows"]),
    ]
    for label, tokens in checks:
        if any(token in manifest_text for token in tokens):
            stack.append(label)
    if not stack:
        for pattern, label in (("*.py", "python"), ("*.ts", "typescript/javascript"), ("*.rs", "rust"), ("*.go", "go")):
            if any(root.rglob(pattern)):
                stack.append(label)
    return stack


def _classify_license(text: str) -> str:
    lower = text.lower()
    if not lower:
        return "unknown"
    if "mit license" in lower or "permission is hereby granted" in lower:
        return "MIT"
    if "apache license" in lower:
        return "Apache-2.0"
    if "gnu general public license" in lower or "gpl" in lower:
        return "GPL-family"
    if "bsd" in lower:
        return "BSD-family"
    return "present-unclassified"


def _scan_risks(root: Path, license_name: str) -> list[str]:
    risks: list[str] = []
    if license_name in {"unknown", "GPL-family"}:
        risks.append(f"license-risk:{license_name}")
    if (root / "package.json").exists() and not any((root / lock).exists() for lock in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock")):
        risks.append("node-manifest-without-lockfile")
    if not any((root / name).exists() for name in ("README.md", "readme.md", "Readme.md")):
        risks.append("missing-readme")
    if not (root / ".github" / "workflows").exists():
        risks.append("missing-ci-workflows")
    return risks


def _classify_fit(stack: list[str], license_name: str, risks: list[str]) -> str:
    if license_name == "GPL-family":
        return "vendor-risk"
    if "license-risk:unknown" in risks:
        return "reference-only"
    if stack:
        return "tool-adoption"
    return "not-fit"


def _next_lane_after_scan(fit_classification: str) -> str:
    return {
        "tool-adoption": "spike-or-feature-with-tests",
        "fork-and-adapt": "spike-before-fork",
        "vendor-risk": "legal/security-review-before-build",
        "reference-only": "research-reference-only",
        "not-fit": "stop-no-build",
    }.get(fit_classification, "repo-intake-read-only-scan")
