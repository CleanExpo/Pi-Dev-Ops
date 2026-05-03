"""swarm/portfolio_pulse.py — RA-1888 (foundation, child of RA-1409).

Daily Portfolio Pulse — generate one markdown briefing per project across the
Unite-Group portfolio + a cross-portfolio synthesis. Founder directive: this
is the single biggest production-value lever currently un-shipped.

Scope of THIS module (RA-1888 foundation only):
  * Public API ``build_pulse(project_id)`` and ``run_all_projects()``
  * File-emission contract (``.harness/portfolio-pulse/<project>/<date>.md``)
  * Section dispatch — each section returns a placeholder until its child
    ticket lands. Sibling children (RA-1889 GitHub, RA-1890 Linear,
    RA-1891 Finance, RA-1892 Synthesis, RA-1893 Telegram delivery) plug
    into the same hooks.
  * Resilient: any single section failure does NOT block the rest of the
    pulse. Missing section = "(none — RA-XXXX not yet wired)".

This module deliberately does NOT call the LLM. The synthesis section
(RA-1892) does that. Foundation just collects + renders.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

log = logging.getLogger("swarm.portfolio_pulse")

REPO_ROOT = Path(__file__).resolve().parents[1]
PULSE_DIR_REL = ".harness/portfolio-pulse"

# Default project list — code-level constant for RA-1888.
# Per-tenant config lands in a later ticket once multi-tenancy rolls out.
DEFAULT_PROJECTS: tuple[str, ...] = (
    "pi-ceo",
    "restoreassist",
    "disaster-recovery",
    "synthex",
    "carsi",
    "unite-group-crm",
    "margot",
)


# ── Data shapes ─────────────────────────────────────────────────────────────


@dataclass
class PulseSection:
    """One section of the daily pulse. Renders as a markdown subsection."""
    name: str
    body_md: str
    error: str | None = None  # populated when a section call raised


@dataclass
class PulseResult:
    """One project's daily pulse + bookkeeping."""
    project_id: str
    date: str  # YYYY-MM-DD UTC
    sections: list[PulseSection] = field(default_factory=list)
    output_path: Path | None = None
    error: str | None = None


# ── Section providers (plug-points for sibling children) ────────────────────


# Each section provider returns (body_md, error). They are SYNC for
# simplicity at the foundation layer — sibling children can wrap async
# work behind a sync facade if needed.

SectionProvider = Callable[[str, Path], tuple[str, str | None]]


def _section_unwired(child: str) -> SectionProvider:
    """Return a placeholder provider that emits a "not yet wired" body.

    Sibling children replace these by registering real providers via
    ``set_section_provider()``.
    """

    def provider(project_id: str, repo_root: Path) -> tuple[str, str | None]:
        return (
            f"_(none — {child} not yet wired; foundation placeholder)_",
            None,
        )

    return provider


# Section name → provider. Foundation registers placeholders; sibling
# children replace via ``set_section_provider()``.
_SECTION_PROVIDERS: dict[str, SectionProvider] = {
    "deploys": _section_unwired("RA-1889"),
    "ci": _section_unwired("RA-1889"),
    "prs": _section_unwired("RA-1889"),
    "linear_movement": _section_unwired("RA-1890"),
    "finance": _section_unwired("RA-1891"),
    "risks": _section_unwired("RA-1892"),
}

# Order of section rendering in the markdown output.
_SECTION_ORDER: tuple[str, ...] = (
    "deploys", "ci", "prs", "linear_movement", "finance", "risks",
)


def set_section_provider(name: str, provider: SectionProvider) -> None:
    """Register a real provider for one section. Used by sibling children."""
    if name not in _SECTION_PROVIDERS:
        log.warning("portfolio_pulse: unknown section %r — registering anyway", name)
    _SECTION_PROVIDERS[name] = provider


# ── Path helpers ────────────────────────────────────────────────────────────


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _pulse_path(project_id: str, date: str, repo_root: Path) -> Path:
    p = repo_root / PULSE_DIR_REL / project_id / f"{date}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ── Section runner ──────────────────────────────────────────────────────────


def _run_section(name: str, project_id: str,
                   repo_root: Path) -> PulseSection:
    provider = _SECTION_PROVIDERS.get(name)
    if provider is None:
        return PulseSection(name=name, body_md="(no provider registered)",
                              error="missing_provider")
    try:
        body, error = provider(project_id, repo_root)
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio_pulse: section %s raised for %s (%s)",
                    name, project_id, exc)
        return PulseSection(name=name, body_md=f"_(error: {exc})_",
                              error=str(exc))
    return PulseSection(name=name, body_md=body or "_(empty)_", error=error)


# ── Markdown rendering ──────────────────────────────────────────────────────


_SECTION_HEADINGS = {
    "deploys":          "Deploys (last 24h)",
    "ci":               "CI state",
    "prs":              "Open PRs",
    "linear_movement":  "Linear movement",
    "finance":          "Revenue & cost",
    "risks":            "Risks & flags",
}


def render_pulse_md(result: PulseResult) -> str:
    """Format a PulseResult as the project's daily markdown briefing."""
    lines = [
        f"# {result.project_id} — Portfolio Pulse {result.date}",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
    ]
    for section in result.sections:
        heading = _SECTION_HEADINGS.get(section.name, section.name.title())
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(section.body_md)
        if section.error:
            lines.append("")
            lines.append(f"_(section error: {section.error})_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ── Public API ──────────────────────────────────────────────────────────────


_SIBLINGS_LOADED = False


def _load_sibling_providers() -> None:
    """Lazy-import every ``portfolio_pulse_*`` sibling so that each one's
    self-registration runs and replaces the foundation placeholders.

    Idempotent — siblings register via ``set_section_provider``, which
    is also idempotent. Errors are logged but never raised; a broken
    sibling must not prevent the rest of the pulse from running.
    """
    global _SIBLINGS_LOADED  # noqa: PLW0603
    if _SIBLINGS_LOADED:
        return
    _SIBLINGS_LOADED = True
    import importlib  # noqa: PLC0415
    import pkgutil  # noqa: PLC0415
    pkg_path = Path(__file__).parent
    for mod in pkgutil.iter_modules([str(pkg_path)]):
        if not mod.name.startswith("portfolio_pulse_"):
            continue
        try:
            importlib.import_module(f"swarm.{mod.name}")
        except Exception as exc:  # noqa: BLE001
            log.warning("portfolio_pulse: sibling %s import failed (%s)",
                        mod.name, exc)


def build_pulse(project_id: str, *,
                  repo_root: Path | None = None,
                  date: str | None = None) -> PulseResult:
    """Build one project's daily pulse — sections + markdown emission.

    Returns a PulseResult with output_path populated on success. Section-
    level failures are recorded on the section but do not raise; only
    catastrophic errors (e.g. inability to write the markdown file) put
    a top-level error on the result.
    """
    _load_sibling_providers()
    rr = repo_root or REPO_ROOT
    when = date or _today_utc()
    result = PulseResult(project_id=project_id, date=when)

    for name in _SECTION_ORDER:
        result.sections.append(_run_section(name, project_id, rr))

    md = render_pulse_md(result)
    try:
        out = _pulse_path(project_id, when, rr)
        out.write_text(md, encoding="utf-8")
        result.output_path = out
    except Exception as exc:  # noqa: BLE001
        result.error = f"write_failed: {exc}"
        log.exception("portfolio_pulse: write failed for %s/%s",
                       project_id, when)
    return result


def run_all_projects(*, projects: tuple[str, ...] | list[str] | None = None,
                       repo_root: Path | None = None,
                       date: str | None = None) -> list[PulseResult]:
    """Build the daily pulse for every project. Sequential (project list
    is small and per-project work is mostly I/O-bound; parallelisation
    can land in a sibling child if pulse runtime grows beyond 60s)."""
    pids = tuple(projects) if projects is not None else DEFAULT_PROJECTS
    results: list[PulseResult] = []
    for pid in pids:
        try:
            results.append(build_pulse(
                pid, repo_root=repo_root, date=date,
            ))
        except Exception as exc:  # noqa: BLE001
            log.exception("portfolio_pulse: build_pulse raised for %s", pid)
            results.append(PulseResult(
                project_id=pid, date=date or _today_utc(),
                error=f"build_pulse_raised: {exc}",
            ))
    log.info(
        "portfolio_pulse: ran %d projects, %d ok, %d errored",
        len(results),
        sum(1 for r in results if not r.error),
        sum(1 for r in results if r.error),
    )
    return results


__all__ = [
    "PulseSection", "PulseResult",
    "DEFAULT_PROJECTS", "SectionProvider",
    "set_section_provider",
    "build_pulse", "run_all_projects",
    "render_pulse_md",
]
