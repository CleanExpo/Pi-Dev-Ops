"""Pipeline Smoke A1–A6 bookkeeping. RA-7596 verify-terminal lives here."""
from __future__ import annotations

from dataclasses import dataclass, field

from scripts.smoke_pipeline_resilience import (
    is_expected_smoke_verify_terminal,
    is_terminal_status,
    note_session_row,
    row_entered_generate,
    terminal_fail_message,
)

GEN_MIN_DURATION_S = 310  # RA-1294 signature: died at exactly 305 s


@dataclass
class PipelineAssertions:
    spawned: bool = False
    entered_generate: bool = False
    entered_generate_at: float | None = None
    generate_duration_s: float | None = None
    reached_complete: bool = False
    documented_verify_terminal: bool = False
    files_modified: int = 0
    pr_url: str | None = None
    last_status: str | None = None
    errors: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    def observe_event(self, event: dict, elapsed_s: float) -> str | None:
        """Retain human-readable phase/error evidence from the session stream."""
        etype = event.get("type", "")
        text = str(event.get("text", "")).strip()
        if etype not in {"phase", "error"} or not text:
            return None
        line = f"  [t+{elapsed_s:.0f}s] {etype}: {text}"
        self.diagnostics.append(line)
        return line

    def summary(self) -> str:
        files_line, pr_line = _a5_a6_lines(self)
        lines = [
            f"A1 session spawned:           {'✓' if self.spawned else '✗'}",
            f"A2 entered generate ≤ 90 s:   {'✓' if self.entered_generate else '✗'}",
            f"A3 generate ≥ {GEN_MIN_DURATION_S}s OR ok: {'✓' if self._a3_ok() else '✗' } (dur={self.generate_duration_s})",
            _a4_line(self),
            files_line,
            pr_line,
        ]
        if self.diagnostics:
            lines.extend(["", "Session diagnostics:", *self.diagnostics[-20:]])
        return "\n".join(lines)

    def _a3_ok(self) -> bool:
        if self.generate_duration_s is None:
            return False
        if self.last_status == "failed" and 295 <= self.generate_duration_s <= 315:
            return False
        return True

    def all_passed(self) -> bool:
        core = (
            self.spawned and self.entered_generate and self._a3_ok()
            and not self.errors
        )
        if self.documented_verify_terminal:
            return core
        return (
            core and self.reached_complete and self.files_modified > 0
            and self.pr_url is not None
        )


def _a4_line(pa: PipelineAssertions) -> str:
    """A4 complete and A4 verify-terminal are different outcomes. Never mix them."""
    if pa.documented_verify_terminal:
        return "A4 verify-terminal (not complete): ✓"
    mark = "✓" if pa.reached_complete else "✗"
    return f"A4 reached complete:          {mark}"


def _a5_a6_lines(pa: PipelineAssertions) -> tuple[str, str]:
    if pa.documented_verify_terminal:
        return (
            "A5 files_modified > 0:        n/a (verify-terminal)",
            "A6 PR URL emitted:            n/a (verify-terminal)",
        )
    return (
        f"A5 files_modified > 0:        "
        f"{'✓' if pa.files_modified > 0 else '✗'} ({pa.files_modified})",
        f"A6 PR URL emitted:            {'✓' if pa.pr_url else '✗'} {pa.pr_url or ''}",
    )


def apply_terminal(pa: PipelineAssertions, me: dict) -> None:
    pa.last_status = me.get("status")
    pa.files_modified = max(pa.files_modified, me.get("files_modified", 0) or 0)
    if pa.last_status == "complete":
        pa.reached_complete = True
        print(f"[A4 PASS] session reached 'complete' with files_modified={pa.files_modified}")
        return
    if is_expected_smoke_verify_terminal(me):
        pa.documented_verify_terminal = True
        print(
            "[A4] verify-terminal (not complete): generate reached "
            "fail-closed workspace verification"
        )
        return
    if is_terminal_status(pa.last_status):
        pa.fail(terminal_fail_message(me))


def observe_row(pa: PipelineAssertions, me: dict, now: float) -> None:
    """Log every poll tick; recover A2 from last_phase if the stream dropped."""
    snap = note_session_row(me)
    pa.diagnostics.append(snap)
    print(f"  [poll t+{now:.0f}s] {snap}")
    if pa.entered_generate or not row_entered_generate(me):
        return
    pa.entered_generate = True
    pa.entered_generate_at = now
    print(f"  [t+{now:.0f}s] ENTERED generate (via /api/sessions last_phase)")


def observe_stream_event(pa: PipelineAssertions, event: dict, now: float) -> None:
    etype = event.get("type", "")
    text = event.get("text", "")
    diagnostic = pa.observe_event(event, now)
    if diagnostic:
        print(diagnostic)
    if etype == "phase":
        _observe_phase(pa, text, now)
    elif etype == "phase_metric" and event.get("phase") == "generate":
        pa.generate_duration_s = event.get("duration_s")
        print(f"  [t+{now:.0f}s] generate metric: dur={pa.generate_duration_s}s cost=${event.get('cost_usd')}")
    elif etype == "push_url" or (etype == "success" and "PR opened" in text):
        pa.pr_url = event.get("url") or text
        print(f"  [t+{now:.0f}s] PR URL: {pa.pr_url}")
    elif etype == "files_modified":
        pa.files_modified = int(event.get("count", 0))


def _observe_phase(pa: PipelineAssertions, text: str, now: float) -> None:
    if "[4/5]" in text or "Running Claude Code" in text:
        pa.entered_generate = True
        pa.entered_generate_at = now
        print(f"  [t+{now:.0f}s] ENTERED generate phase")
    elif "[5/5]" in text:
        print(f"  [t+{now:.0f}s] {text}")
