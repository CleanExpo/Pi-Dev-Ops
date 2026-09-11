"""`gate_parity_lint.ci_steps()` must see every `run:` step, under its own name.

Found 2026-09-11 by reading `.github/scripts/gate_parity_lint.py:98-124`, then
confirmed by the fixture below. Two defects in the same regex-based parser:

1. A step written as `- run: cmd` (name and run combined on one list-item line,
   no separate `- name:` line) was INVISIBLE. The old `run:` regex required the
   line to start with optional whitespace then the literal `run:` — a leading
   `-` is not whitespace, so it never matched. A whole class of legally-shaped
   GitHub Actions step silently never entered the parity check at all.

2. An unnamed step — any step whose OWN name could not be read, including the
   one above once it partially matched something else — inherited the
   PREVIOUS step's `name` variable, because the old code only ever SET `name`
   on a match and never reset it on a new list item. Inheriting the name also
   inherits that name's map exemption in `.github/gate-parity.map.json`, so a
   genuinely new, unmapped CI command could ride in under an already-approved
   entry and this whole gate — built specifically to catch new unmapped
   commands (rules/truth-hacking.md Law 5: recurrence is a defect in the
   harness) — would say nothing.

Both are load-bearing: this gate exists ONLY to fail on drift, so a parser
that silently drops or misattributes a step is the exact failure mode it was
built to prevent, one level down.
"""
import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "gate_parity_lint.py"
_spec = importlib.util.spec_from_file_location("gate_parity_lint", _MODULE_PATH)
gate_parity_lint = importlib.util.module_from_spec(_spec)
sys.modules["gate_parity_lint"] = gate_parity_lint
_spec.loader.exec_module(gate_parity_lint)


FIXTURE = """\
jobs:
  demo:
    steps:
      - name: Mapped step
        run: echo mapped
      - run: echo shorthand_no_name
      - name: Second mapped step
        run: |
          echo block-scalar
"""


def test_shorthand_run_step_is_not_invisible(tmp_path):
    """Defect 1 — `- run: cmd` must produce a step, not vanish."""
    wf = tmp_path / "ci.yml"
    wf.write_text(FIXTURE)
    steps = gate_parity_lint.ci_steps(wf)
    commands = [cmd for _, cmd in steps]
    assert "echo shorthand_no_name" in commands, (
        "the `- run:` shorthand step was dropped entirely — it cannot be checked "
        "for parity if the parser never sees it"
    )


def test_unnamed_step_does_not_inherit_the_previous_names_exemption(tmp_path):
    """Defect 2 — an unnamed step must be reported as unnamed, never as its neighbour."""
    wf = tmp_path / "ci.yml"
    wf.write_text(FIXTURE)
    # `ci_steps` returns (name, cmd) pairs — key by command, since names collide
    # by design in this fixture (that collision IS the defect under test).
    name_by_cmd = {cmd: name for name, cmd in gate_parity_lint.ci_steps(wf)}
    assert name_by_cmd["echo shorthand_no_name"] != "Mapped step", (
        "the unnamed step inherited the PRECEDING step's name — and with it, "
        "that step's map exemption"
    )
    assert name_by_cmd["echo shorthand_no_name"] == "<unnamed step>"


def test_named_steps_either_side_are_unaffected(tmp_path):
    """Negative control: the fix must not break the ordinary two-line form."""
    wf = tmp_path / "ci.yml"
    wf.write_text(FIXTURE)
    name_by_cmd = {cmd: name for name, cmd in gate_parity_lint.ci_steps(wf)}
    assert name_by_cmd["echo mapped"] == "Mapped step"
    assert name_by_cmd["echo block-scalar"] == "Second mapped step"


def test_all_four_steps_are_present(tmp_path):
    """Positive control on count: nothing merged or dropped besides the target line."""
    wf = tmp_path / "ci.yml"
    wf.write_text(FIXTURE)
    steps = gate_parity_lint.ci_steps(wf)
    assert len(steps) == 3, steps


def test_job_level_name_is_not_read_as_a_step(tmp_path):
    """Regression: an earlier version of this fix made `name:` dash-optional to
    catch the `- id: x` / `name: Y` / `run: z` shape, and that ALSO started
    matching job- and workflow-level `name:` keys, which sit at the same
    indentation with no dash. Caught by re-running against the real ci.yml
    (`gate_parity_lint.py` flagged a phantom `Frontend (tsc + eslint + build)`
    step with an empty command) before this test existed to pin it.
    """
    wf = tmp_path / "ci.yml"
    wf.write_text(
        "name: A workflow-level name, not a step\n"
        "jobs:\n"
        "  demo:\n"
        "    name: A job-level name, also not a step\n"
        "    steps:\n"
        "      - name: The only real step\n"
        "        run: echo real\n",
    )
    steps = gate_parity_lint.ci_steps(wf)
    assert steps == [("The only real step", "echo real")], steps


# ── Defect C: gate_parity_lint.py must actually run somewhere CI cannot skip ──
#
# `scripts/handoff-loop.sh` SKIPs "gate-parity" when Python deps are absent
# locally (honest — the script's own SUMMARY then reports non-READY, so it is
# not a silent pass on THIS script's part). But nothing forces a developer to
# run handoff-loop.sh at all, and until this test existed gate_parity_lint.py
# had never run anywhere else — not CI, not a hook (this repo's own history:
# 88423dd9 added a CI step with no map entry and the runner still printed
# READY, because the checker that would have caught it never executed).

CI_YML = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


def test_an_empty_parse_refuses_instead_of_passing(monkeypatch, capsys):
    """Defect 3 — a parser that stops matching must FAIL this gate.

    `bad = len(unmapped) + len(dangling)` cannot tell "nothing is wrong" from
    "nothing was read": both leave every bucket empty, so a regex that quietly
    stops matching printed `gate-parity passed`. That is the same class of
    defect as 1 and 2 above, one level up — and by Law 5 a recurrence is a
    hole in the harness, not bad luck.
    """
    monkeypatch.setattr(gate_parity_lint, "ci_steps", lambda wf: [])
    monkeypatch.setattr(sys, "argv", ["gate_parity_lint.py"])

    assert gate_parity_lint.main() == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "passed" not in out


def test_gate_parity_lint_is_wired_into_ci():
    """CI itself must invoke the checker — not rely solely on a skippable local run."""
    assert "gate_parity_lint.py" in CI_YML.read_text(), (
        "gate_parity_lint.py is not invoked anywhere in ci.yml — the one gate whose "
        "job is to catch missing local coverage has none of its own"
    )


def test_gate_parity_lint_passes_against_the_real_repo():
    """The check must actually be green here, not merely present in the file."""
    gates = gate_parity_lint.local_gate_names()
    entries = gate_parity_lint.load_map().get("steps", {})
    _, _, dangling, unmapped = gate_parity_lint.classify(gates, entries)
    assert not dangling, dangling
    assert not unmapped, unmapped
