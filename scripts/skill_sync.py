"""Portfolio-wide specialised skill scan and approved promotion.

Read-only scan mode inventories project-local Claude/agent skills across the
portfolio registry. Apply mode promotes only report rows explicitly checked for
approval and leaves project/global copies untouched.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.server import config_loader  # noqa: E402

try:
    import yaml
except Exception:  # pragma: no cover - PyYAML is a project dependency.
    yaml = None


PROJECTS_FILE = config_loader.PROJECTS_JSON
CANONICAL_SKILLS = REPO_ROOT / "skills"
REPORT_DIR = REPO_ROOT / ".harness" / "skill-sync" / "reports"
APPLY_DIR = REPO_ROOT / ".harness" / "skill-sync" / "applies"
DEFAULT_GLOBAL_SKILLS = Path.home() / ".claude" / "skills"

SCAN_PATTERNS = (
    ".claude/skills/*/SKILL.md",
    ".agents/skills/*/SKILL.md",
    "skills/*/SKILL.md",
)
CLASSIFICATIONS = {
    "CANONICAL_IDENTICAL",
    "PROJECT_UNIQUE",
    "NAME_CONFLICT",
    "PROJECT_SPECIFIC",
    "INVALID",
    "OBSOLETE_CANDIDATE",
}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}
REF_RE = re.compile(r"\[[^\]]+\]\(([^)#][^)#]*)(?:#[^)]+)?\)|`([^`\s]+\.(?:md|json|ya?ml|txt|sh|py|ts|tsx|js|jsx|csv))`")
SIBLING_REF_ROOTS = {"assets", "examples", "references", "scripts", "templates"}
APPROVAL_RE = re.compile(
    r"^- \[[xX]\] APPROVE_PROMOTE name=(?P<name>[a-z0-9_-]+) "
    r"source=(?P<source>.+?) folder_sha256=(?P<folder>[0-9a-f]{64})"
    r"(?: resolution=(?P<resolution>[a-z0-9_-]+))?"
)


@dataclass(frozen=True)
class RepositoryRef:
    project_id: str
    repo: str
    path: Path | None
    status: str


@dataclass
class SkillRecord:
    name: str
    source_repository: str
    source_project_id: str
    source_path: str
    relative_source_path: str
    folder_sha256: str
    skill_sha256: str
    frontmatter: dict[str, Any]
    referenced_sibling_files: list[str] = field(default_factory=list)
    missing_references: list[str] = field(default_factory=list)
    canonical_match: str | None = None
    canonical_folder_sha256: str | None = None
    classification: str = "PROJECT_UNIQUE"
    disposition: str = ""
    invalid_reasons: list[str] = field(default_factory=list)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    def fallback_fields(error: str | None = None) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for line in raw.splitlines():
            if ":" in line and not line.startswith(" "):
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()
        if error:
            fields["__frontmatter_error__"] = error
        return fields

    if yaml is None:
        return fallback_fields(), body
    try:
        loaded = yaml.safe_load(raw) or {}
    except Exception as exc:
        return fallback_fields(str(exc).splitlines()[0]), body
    return loaded if isinstance(loaded, dict) else {}, body


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def folder_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and not _is_skipped(p)):
        rel = path.relative_to(folder).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def load_repositories(projects_file: Path = PROJECTS_FILE, repo_root: Path = REPO_ROOT) -> list[RepositoryRef]:
    data = json.loads(projects_file.read_text(encoding="utf-8"))
    seen: set[str] = set()
    repos: list[RepositoryRef] = []
    for project in data.get("projects", []):
        repo = str(project.get("repo") or "").strip()
        if not repo or repo in seen:
            continue
        seen.add(repo)
        path = resolve_local_repo(repo, repo_root)
        repos.append(
            RepositoryRef(
                project_id=str(project.get("id") or repo.split("/")[-1]),
                repo=repo,
                path=path,
                status="scanned" if path else "missing-local-checkout",
            )
        )
    return sorted(repos, key=lambda r: (r.repo.lower(), r.project_id.lower()))


def resolve_local_repo(repo: str, repo_root: Path = REPO_ROOT) -> Path | None:
    if repo.lower() == "cleanexpo/pi-dev-ops":
        return repo_root
    basename = repo.split("/")[-1]
    home = Path.home()
    candidates = [
        home / basename,
        home / basename.lower(),
        home / basename.upper(),
        home / basename.title(),
        repo_root.parent / basename,
        repo_root.parent / basename.lower(),
        repo_root.parent / basename.upper(),
    ]
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate.resolve()
    for child in sorted(home.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir() and child.name.lower() == basename.lower() and (child / ".git").exists():
            return child.resolve()
    return None


def collect_references(skill_md: Path, skill_dir: Path) -> tuple[list[str], list[str]]:
    text = skill_md.read_text(encoding="utf-8")
    refs: set[str] = set()
    missing: set[str] = set()
    for match in REF_RE.finditer(text):
        raw = (match.group(1) or match.group(2) or "").strip()
        if not raw or raw.startswith(("http://", "https://", "mailto:", "#", "/", "~", "../")):
            continue
        first_part = raw.split("/", 1)[0]
        is_markdown_link = bool(match.group(1))
        if not is_markdown_link and first_part not in SIBLING_REF_ROOTS:
            continue
        ref_path = (skill_dir / raw).resolve()
        try:
            rel = ref_path.relative_to(skill_dir.resolve()).as_posix()
        except ValueError:
            continue
        refs.add(rel)
        if not ref_path.exists():
            missing.add(rel)
    return sorted(refs), sorted(missing)


def scan_repositories(
    repo_root: Path = REPO_ROOT,
    projects_file: Path = PROJECTS_FILE,
    global_skills_dir: Path = DEFAULT_GLOBAL_SKILLS,
) -> tuple[list[RepositoryRef], list[SkillRecord], list[str]]:
    repositories = load_repositories(projects_file, repo_root)
    canonical_hashes = {
        child.name: folder_hash(child)
        for child in sorted((repo_root / "skills").iterdir())
        if child.is_dir() and (child / "SKILL.md").exists()
    }

    records: list[SkillRecord] = []
    for repo in repositories:
        if not repo.path:
            continue
        for pattern in SCAN_PATTERNS:
            for skill_md in sorted(repo.path.glob(pattern), key=lambda p: p.as_posix()):
                if _is_skipped(skill_md):
                    continue
                records.append(scan_skill(repo, skill_md, repo_root, canonical_hashes))

    records.sort(key=lambda r: (r.source_repository.lower(), r.relative_source_path.lower()))
    return repositories, records, real_global_directories(repo_root / "skills", global_skills_dir)


def scan_skill(
    repo: RepositoryRef,
    skill_md: Path,
    repo_root: Path,
    canonical_hashes: dict[str, str],
) -> SkillRecord:
    skill_dir = skill_md.parent
    text = skill_md.read_text(encoding="utf-8")
    frontmatter, _body = parse_frontmatter(text)
    name = str(frontmatter.get("name") or skill_dir.name)
    invalid: list[str] = []
    if not frontmatter:
        invalid.append("missing-or-invalid-frontmatter")
    if frontmatter.get("__frontmatter_error__"):
        invalid.append(f"invalid-yaml-frontmatter:{frontmatter['__frontmatter_error__']}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        invalid.append("invalid-skill-name")
    if name != skill_dir.name:
        invalid.append(f"name-folder-mismatch:{name}!={skill_dir.name}")
    if not str(frontmatter.get("description") or "").strip():
        invalid.append("missing-description")
    refs, missing = collect_references(skill_md, skill_dir)
    invalid.extend(f"missing-reference:{ref}" for ref in missing)

    canonical_dir = repo_root / "skills" / name
    canonical_match = str(canonical_dir.relative_to(repo_root)) if canonical_dir.exists() else None
    current_folder_hash = folder_hash(skill_dir)
    current_skill_hash = sha256_file(skill_md)
    canonical_folder_sha = canonical_hashes.get(name)

    classification = classify_skill(
        repo=repo,
        skill_md=skill_md,
        repo_root=repo_root,
        name=name,
        invalid=invalid,
        folder_sha=current_folder_hash,
        canonical_folder_sha=canonical_folder_sha,
        frontmatter=frontmatter,
        body=text,
    )
    return SkillRecord(
        name=name,
        source_repository=repo.repo,
        source_project_id=repo.project_id,
        source_path=str(skill_dir),
        relative_source_path=skill_dir.relative_to(repo.path).as_posix() if repo.path else str(skill_dir),
        folder_sha256=current_folder_hash,
        skill_sha256=current_skill_hash,
        frontmatter=frontmatter,
        referenced_sibling_files=refs,
        missing_references=missing,
        canonical_match=canonical_match,
        canonical_folder_sha256=canonical_folder_sha,
        classification=classification,
        disposition=recommended_disposition(classification, name, repo.repo),
        invalid_reasons=invalid,
    )


def classify_skill(
    repo: RepositoryRef,
    skill_md: Path,
    repo_root: Path,
    name: str,
    invalid: list[str],
    folder_sha: str,
    canonical_folder_sha: str | None,
    frontmatter: dict[str, Any],
    body: str,
) -> str:
    if invalid:
        return "INVALID"
    canonical_skill = repo_root / "skills" / name / "SKILL.md"
    if canonical_skill == skill_md.resolve():
        return "CANONICAL_IDENTICAL"
    if canonical_folder_sha:
        return "CANONICAL_IDENTICAL" if canonical_folder_sha == folder_sha else "NAME_CONFLICT"
    project_token = (repo.project_id or repo.repo.split("/")[-1]).lower().replace("-", "")
    body_flat = body.lower().replace("-", "")
    name_flat = name.lower().replace("-", "")
    if project_token and (project_token in body_flat or project_token in name_flat):
        return "PROJECT_SPECIFIC"
    if frontmatter.get("disable-model-invocation") and ".claude/skills/" in skill_md.as_posix():
        return "PROJECT_SPECIFIC"
    return "PROJECT_UNIQUE"


def recommended_disposition(classification: str, name: str, repo: str) -> str:
    if classification == "CANONICAL_IDENTICAL":
        return "Already represented by Pi-Dev-Ops canonical skill; keep or retire local duplicate manually."
    if classification == "PROJECT_SPECIFIC":
        return "Promote only if portfolio-reusable as a project-specific canonical skill."
    if classification == "PROJECT_UNIQUE":
        return "Eligible for promotion after skill-authoring-standard review."
    if classification == "NAME_CONFLICT":
        return "Do not auto-promote; requires explicit conflict resolution."
    if classification == "INVALID":
        return "Fix frontmatter/references before promotion."
    return f"Review whether {name} from {repo} is obsolete."


def real_global_directories(canonical_skills_dir: Path, global_skills_dir: Path) -> list[str]:
    if not global_skills_dir.exists() or not canonical_skills_dir.exists():
        return []
    occupied: list[str] = []
    for child in sorted(canonical_skills_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or not (child / "SKILL.md").exists():
            continue
        target = global_skills_dir / child.name
        if target.exists() and target.is_dir() and not target.is_symlink():
            occupied.append(str(target))
    return occupied


def write_report(
    repositories: list[RepositoryRef],
    records: list[SkillRecord],
    global_real_dirs: list[str],
    repo_root: Path = REPO_ROOT,
    report_date: dt.date | None = None,
) -> Path:
    report_date = report_date or dt.date.today()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"SKILL-SYNC-{report_date.isoformat()}.md"

    lines: list[str] = [
        f"# Skill Sync Report — {report_date.isoformat()}",
        "",
        "Read-only scan output. Only checked `APPROVE_PROMOTE` rows are eligible for apply mode.",
        "",
        "## Repositories Scanned",
        "",
        "| Project | Repo | Local path | Status |",
        "|---|---|---|---|",
    ]
    for repo in repositories:
        lines.append(f"| {repo.project_id} | {repo.repo} | {repo.path or 'missing'} | {repo.status} |")

    lines.extend([
        "",
        "## Skills Discovered",
        "",
        "| Classification | Skill | Repo | Path | Folder SHA-256 | SKILL.md SHA-256 | Canonical match | Disposition |",
        "|---|---|---|---|---|---|---|---|",
    ])
    for record in records:
        lines.append(
            "| {classification} | {name} | {repo} | `{path}` | `{folder}` | `{skill}` | {match} | {disp} |".format(
                classification=record.classification,
                name=record.name,
                repo=record.source_repository,
                path=record.relative_source_path,
                folder=record.folder_sha256,
                skill=record.skill_sha256,
                match=record.canonical_match or "missing",
                disp=record.disposition.replace("|", "\\|"),
            )
        )

    lines.extend(["", "## Unique Skills Missing From Pi-Dev-Ops", ""])
    missing = [r for r in records if r.classification in {"PROJECT_UNIQUE", "PROJECT_SPECIFIC"}]
    if missing:
        for record in missing:
            lines.append(f"- `{record.name}` from `{record.source_repository}` at `{record.relative_source_path}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Same-Name Different-Content Conflicts", ""])
    conflicts = [r for r in records if r.classification == "NAME_CONFLICT"]
    if conflicts:
        for record in conflicts:
            lines.append(
                f"- `{record.name}`: source `{record.folder_sha256}`, canonical `{record.canonical_folder_sha256}` "
                f"from `{record.source_repository}` `{record.relative_source_path}`"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Real Global Directories Occupying Canonical Skill Paths", ""])
    if global_real_dirs:
        for path in global_real_dirs:
            lines.append(f"- `{path}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Missing References", ""])
    missing_refs = [r for r in records if r.missing_references]
    if missing_refs:
        for record in missing_refs:
            lines.append(f"- `{record.name}` `{record.relative_source_path}`: {', '.join(record.missing_references)}")
    else:
        lines.append("- None")

    lines.extend(["", "## Invalid Frontmatter Or Skill Structure", ""])
    invalid = [r for r in records if r.invalid_reasons]
    if invalid:
        for record in invalid:
            lines.append(f"- `{record.name}` `{record.relative_source_path}`: {', '.join(record.invalid_reasons)}")
    else:
        lines.append("- None")

    lines.extend(["", "## Approval Rows", ""])
    promotable = [r for r in records if r.classification in {"PROJECT_UNIQUE", "PROJECT_SPECIFIC"}]
    if promotable:
        for record in promotable:
            checked = "x" if record.name == "carsi-course-production" and record.source_repository.lower().endswith("/carsi") else " "
            note = " — pre-approved by this task request" if checked == "x" else ""
            lines.append(
                f"- [{checked}] APPROVE_PROMOTE name={record.name} source={record.source_path} "
                f"folder_sha256={record.folder_sha256}{note}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Evidence JSON", "", "```json"])
    lines.append(json.dumps([asdict(r) for r in records], indent=2, sort_keys=True))
    lines.extend(["```", ""])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def parse_approved_rows(report_path: Path) -> list[dict[str, str]]:
    approvals: list[dict[str, str]] = []
    for line in report_path.read_text(encoding="utf-8").splitlines():
        match = APPROVAL_RE.match(line.strip())
        if not match:
            continue
        approvals.append({k: v for k, v in match.groupdict().items() if v})
    return approvals


def review_skill_folder(skill_dir: Path) -> list[str]:
    skill_md = skill_dir / "SKILL.md"
    failures: list[str] = []
    if not skill_md.exists():
        return ["missing SKILL.md"]
    text = skill_md.read_text(encoding="utf-8")
    frontmatter, _body = parse_frontmatter(text)
    if not frontmatter:
        failures.append("missing or invalid frontmatter")
    if frontmatter.get("name") != skill_dir.name:
        failures.append("frontmatter name must match folder name")
    if not frontmatter.get("description"):
        failures.append("missing description")
    if len(text.splitlines()) > 200:
        failures.append("SKILL.md exceeds 200 lines")
    _refs, missing = collect_references(skill_md, skill_dir)
    failures.extend(f"missing referenced file: {ref}" for ref in missing)
    return failures


def apply_report(report_path: Path, repo_root: Path = REPO_ROOT, apply_dir: Path = APPLY_DIR) -> Path:
    approvals = parse_approved_rows(report_path)
    apply_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "report": str(report_path),
        "created": [],
        "changed": [],
        "skipped": [],
        "conflicted": [],
        "failed": [],
        "review": {},
        "manifest_regeneration": None,
    }
    for approval in approvals:
        name = approval["name"]
        source = Path(approval["source"]).expanduser().resolve()
        expected_hash = approval["folder"]
        dest = repo_root / "skills" / name
        if not (source / "SKILL.md").exists():
            manifest["failed"].append({"name": name, "reason": "source missing SKILL.md", "source": str(source)})
            continue
        actual_hash = folder_hash(source)
        if actual_hash != expected_hash:
            manifest["failed"].append({"name": name, "reason": "source hash changed", "expected": expected_hash, "actual": actual_hash})
            continue
        review_failures = review_skill_folder(source)
        manifest["review"][name] = {"status": "PASS" if not review_failures else "FAIL", "failures": review_failures}
        if review_failures:
            manifest["failed"].append({"name": name, "reason": "skill-authoring-standard review failed", "failures": review_failures})
            continue
        if dest.exists():
            if folder_hash(dest) == actual_hash:
                manifest["skipped"].append({"name": name, "path": str(dest), "reason": "canonical already identical"})
                continue
            if approval.get("resolution") != "overwrite":
                manifest["conflicted"].append({"name": name, "path": str(dest), "reason": "canonical exists with different content"})
                continue
            shutil.rmtree(dest)
            shutil.copytree(source, dest, symlinks=True)
            manifest["changed"].append({"name": name, "path": str(dest), "reason": "approved overwrite"})
        else:
            shutil.copytree(source, dest, symlinks=True)
            manifest["created"].append({"name": name, "path": str(dest)})

    manifest["manifest_regeneration"] = regenerate_agentskills(repo_root)
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest_path = apply_dir / f"SKILL-SYNC-APPLY-{timestamp}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def regenerate_agentskills(repo_root: Path) -> dict[str, Any]:
    module = repo_root / "swarm" / "agentskills_manifest.py"
    if not module.exists():
        return {"status": "skipped", "reason": "swarm/agentskills_manifest.py not present"}
    result = subprocess.run(
        [sys.executable, "-m", "swarm.agentskills_manifest"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "status": "ok" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def run_scan(args: argparse.Namespace) -> int:
    repositories, records, global_real_dirs = scan_repositories(
        repo_root=args.repo_root,
        projects_file=args.projects_file,
        global_skills_dir=args.global_skills_dir,
    )
    report = write_report(repositories, records, global_real_dirs, repo_root=args.repo_root, report_date=args.date)
    print(f"Wrote {report}")
    print(f"Repositories scanned: {sum(1 for r in repositories if r.path)} / {len(repositories)}")
    print(f"Skills discovered: {len(records)}")
    return 0


def run_apply(args: argparse.Namespace) -> int:
    manifest = apply_report(args.report, repo_root=args.repo_root)
    print(f"Wrote {manifest}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan and promote portfolio specialised skills safely.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--projects-file", type=Path, default=PROJECTS_FILE)
    parser.add_argument("--global-skills-dir", type=Path, default=DEFAULT_GLOBAL_SKILLS)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Read-only portfolio skill scan.")
    scan.add_argument("--date", type=lambda s: dt.date.fromisoformat(s), default=None)
    scan.set_defaults(func=run_scan)
    apply = sub.add_parser("apply", help="Promote only checked approval rows from a report.")
    apply.add_argument("report", type=Path)
    apply.set_defaults(func=run_apply)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.repo_root = args.repo_root.resolve()
    args.projects_file = args.projects_file.resolve()
    args.global_skills_dir = args.global_skills_dir.expanduser().resolve()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
