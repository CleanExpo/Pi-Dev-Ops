#!/usr/bin/env python3
"""Guards for the /spm front door: tiering, the build bar, seat rules and the contract lock.

Each test names the independent-review finding (Codex, 18/10/2026) it prevents from returning.
Run: python3 skills/spm/scripts/test_spm_core.py
"""
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPM = HERE.parent
_spec = importlib.util.spec_from_file_location("tier", HERE / "tier.py")
tier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tier)


def rendered(md):
    """What a reader sees: no HTML comments (closed or unclosed) and no fenced code."""
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    md = re.sub(r"<!--.*\Z", "", md, flags=re.S)
    return re.sub(r"^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[`~]*[ \t]*$", "", md, flags=re.S | re.M)


class TierTests(unittest.TestCase):
    AXES = [(f, i, n, x, s) for f in range(3) for i in range(3) for n in range(3) for x in range(3) for s in range(3)]

    def test_every_axis_combination_has_exactly_one_tier(self):
        # P1-SPM-TIER-GAP: F0 I0 N0 X0 S1 matched no tier.
        self.assertEqual(len(self.AXES), 243)
        for axes in self.AXES:
            self.assertIn(tier.tier(*axes), tier.TIERS)
        self.assertEqual(tier.tier(0, 0, 0, 0, 1), "T1")
        self.assertEqual(tier.tier(0, 0, 0, 0, 2), "T3")

    def test_a_pin_never_drops_a_mandatory_seat(self):
        # P1-SPM-OVERRIDE-DROPS-SECURITY and P1-SPM-TIER-PIN-DROPS-JUDGE.
        self.assertEqual(tier.effective((0, 0, 0, 0, 2), "T0"), ("T3", "floor-kept"))
        self.assertEqual(tier.effective((0, 0, 2, 2, 0), "T0"), ("T3", "floor-kept"))
        for axes in self.AXES:
            computed = tier.tier(*axes)
            for pin in tier.TIERS:
                got, _ = tier.effective(axes, pin)
                if computed in ("T2", "T3"):
                    self.assertGreaterEqual(tier.TIERS.index(got), tier.TIERS.index(computed), (axes, pin))


class ShapeTests(unittest.TestCase):
    def setUp(self):
        self.md = (SPM / "SKILL.md").read_text()
        self.view = rendered(self.md)
        self.board = rendered((SPM / "references" / "moa-board.md").read_text())
        self.lev = rendered((SPM / "references" / "leveling.md").read_text())

    def sizing_rows(self):
        lines = self.view.split("\n")
        i = next(n for n, l in enumerate(lines) if l.startswith("## 0. Size it first")) + 1
        while i < len(lines) and not lines[i].startswith("| "):
            if lines[i].startswith("#"):
                return []
            i += 1
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            if not re.fullmatch(r"\|(\s*:?-+:?\s*\|)+", lines[i].strip()):
                rows.append([c.strip() for c in lines[i].split("|")[1:-1]])
            i += 1
        return rows

    def test_learn_lane_routes_to_teach(self):
        learn = [r for r in self.sizing_rows() if r[1] == "**Learn**"]
        self.assertTrue(learn and "`teach`" in learn[0][2])

    def test_rendered_view_ignores_comments_and_fences(self):
        # P0 comment / fence / unclosed-comment decoys.
        self.assertEqual(rendered("a\n<!--\nb"), "a\n")
        self.assertNotIn("x", rendered("```md\nx\n```\n"))

    def test_build_bar_is_the_judge_hard_line(self):
        # P1-SPM-APPROVAL-BAR and the sub-100 phrasing escapes.
        judge = (SPM.parent / "judge" / "SKILL.md").read_text()
        self.assertIn("100/100 is the only build bar", judge, "positive control")
        for path in [SPM / "SKILL.md", *sorted((SPM / "references").glob("*.md"))]:
            text = rendered(path.read_text())
            self.assertEqual(re.findall(r"\b([1-9]\d?)\s*/\s*100\b", text), [], path.name)
            self.assertNotRegex(text, r"\b9\d\+?\s*\**\s*APPROVE BUILD", path.name)
        self.assertIn("APPROVE BUILD only at\n   a real 100/100", self.md)

    def test_a_plan_only_request_stops_at_the_spec(self):
        # P1-SPM-PLAN-AUTO-BUILD.
        self.assertIn("only when the request already authorises implementation", self.view)
        self.assertIn("plan-only", self.view)

    def test_loadout_checks_in_by_name_never_all(self):
        # P1-SPM-CHECKIN-ALL-REMOVES-OTHER-SESSION-SKILLS.
        self.assertIn("checkin <name>", self.view)
        self.assertNotRegex(self.view.replace("Never `--all`", ""), r"checkin --all")

    def test_mandatory_seats_survive_pins_overrides_budget_and_degradation(self):
        # T1 security/ops seats, project override, cost guard and degraded-bench findings.
        self.assertRegex(self.board, r"T1 seats \{[^}]*\+ 4 whenever S≥1[^}]*\+ 8 whenever I≥1")
        self.assertRegex(self.board, r"never remove a mandatory seat:[^.]*2 and 5 at T3")
        self.assertRegex(self.board, r"degraded\s+bench caps the decision at APPROVE EXPERIMENT")
        self.assertIn("mandatory seat is ever dropped", self.lev)
        self.assertIn("never dropping a mandatory seat", self.view)

    def test_pre_contract_steps_stay_inside_what_the_done_gate_allows(self):
        # Core review r1 P1-SPM-DONE-CONTRACT-ORDER: in a repo with a .claude/done tree and no locked
        # contract, donectl preflight DENIES skill_shelf find and spec writes outside .claude/done
        # (probed in Unite-Group 18/10/2026) and ALLOWS grep and writes under .claude/done.
        self.assertIn("`.claude/done/spm/<YYYY-MM-DD>-<slug>/spec.md`", self.view)
        self.assertRegex(self.view, r"grep -n -i '<verb>' ~/\.claude/skills/index\.md")
        # Core review r2 P1-SPM-DONE-CONTRACT-ORDER-ENGINEERING-GATE: tier.py and engineering_gate.py
        # are DENIED with no locked contract (probed); donectl itself is always ALLOWED. So a Tier-1
        # spec-work contract is locked at step 1 and revised into the build contract at step 10.
        self.assertRegex(self.view, r"open and lock a Tier-1 \*\*spec-work contract\*\* now")
        self.assertIn("`donectl revise` supersedes the spec-work contract", self.view)
        self.assertLess(self.view.index("spec-work contract** now"), self.view.index("**Convene the bench.**"),
                        "the spec-work contract must be locked before the tier script runs")

    def test_a_micro_pin_never_shrinks_a_t2_or_t3_spec(self):
        # Core review r4, P1-SPM-MICRO-PIN-CONFLICTS-WITH-T3-FULL-SPEC: micro + production + tenancy
        # scores T3 and the pin keeps the floor, so the format must follow the tier, not the pin.
        self.assertEqual(tier.tier(0, 2, 0, 0, 2), "T3")
        self.assertRegex(self.view, r"a\s+`micro` pin never shrinks a T2/T3 request: when `tier\.py` returns T2 or T3, the full spec is required")

    def test_revise_never_drops_a_contract_spm_did_not_open(self):
        # Core review r4, P1-SPM-REVISE-CAN-DROP-EXISTING-DONE-CRITERIA.
        self.assertIn("note the `work_id` it prints", self.view)
        self.assertRegex(self.view, r"Revise only when the active contract is the spec-work `work_id` from step\s+1\.")
        self.assertRegex(self.view, r"carries every\s+existing criterion forward")
        # Core review r5, P1-SPM-BUILD-UNDER-UNRELATED-LOCK-HAS-NO-NEW-AC: an old lock cannot see new criteria.
        self.assertRegex(self.view, r"do not build under it: it cannot\s+see the new criteria")
        self.assertRegex(self.view, r"build only once that revision is locked")
        self.assertNotIn("keep it: build under it", self.view)

    def test_micro_spec_carries_lockable_acceptance(self):
        # Core review r6, P1-SPM-MICRO-AC-GAP: a micro spec with no checks cannot lock a contract.
        self.assertIn("`container · behaviour · UI · kicker · acceptance`", self.view)
        self.assertRegex(self.view, r"acceptance = each check with the command that proves it, which become the Done criteria")

    def test_done_tree_is_initialised_before_the_spec_contract(self):
        # Core review r6, P1-SPM-NO-DONE-INIT-ROUTE: revise/lock fail in a repo with no Done tree.
        self.assertRegex(self.view, r"run `donectl init` first when\s+the\s+repo\s+has\s+no\s+`\.claude/done/`\s+tree")
        self.assertLess(self.view.index("donectl init"), self.view.index("spec-work contract** now"))

    def test_an_existing_draft_is_never_replaced(self):
        # Core review r7, P1-SPM-DRAFT-REBOUND-BY-SPEC-PREFLIGHT.
        self.assertRegex(self.view, r"An active DRAFT is existing work: continue it when it is\s+this request's, otherwise stop")
        self.assertRegex(self.view, r"never\s+start over it")
        self.assertLess(self.view.index("An active DRAFT is existing work"), self.view.index("spec-work contract** now"))

    def test_a_post_gate_amendment_stops_the_build(self):
        # Core review r7, P1-SPM-AMENDED-SPEC-OUTRUNS-ENGINEERING-AND-DONE.
        self.assertRegex(self.view, r"An amendment after step 9 stops the build: re-run the engineering gate\s+on the new spec, then revise and relock Done")
        tmpl = (SPM / "references" / "spec-template.md").read_text()
        self.assertRegex(tmpl, r"amends this spec and stops the build:\s+the engineering gate re-runs on the amended spec")

    def test_a_missing_mandatory_seat_blocks_build(self):
        # Core review r8, P1-SPM-MANDATORY-SECURITY-SEAT-ABSTAIN-PERMITS-BUILD: S=1 scores T1 and seats 4.
        self.assertEqual(tier.tier(0, 0, 0, 0, 1), "T1")
        self.assertRegex(self.board, r"A mandatory\s+seat that abstains, fails or never returns blocks APPROVE BUILD at every tier")
        self.assertRegex(self.board, r"caps\s+at APPROVE EXPERIMENT until that seat returns a valid contract")

    def test_front_door_commands_run_as_written(self):
        # Core review r9, P1-SPM-FRONT-DOOR-COMMANDS-NOT-EXECUTABLE: bare names were not on PATH.
        forms = {
            "donectl": ("python3", "done-harness/scripts/donectl.py"),
            "skill_shelf.mjs": ("node", "skill-selector/scripts/skill_shelf.mjs"),
            "engineering_gate.py": ("python3", "engineering-requirements/scripts/engineering_gate.py"),
        }
        skills = SPM.parent
        for name, (interp, rel) in forms.items():
            self.assertRegex(self.view, r"\s+".join(map(re.escape, f"`{name}` = `{interp} ~/.claude/skills/{rel}`".split(" "))), name)
            target = skills / rel
            self.assertTrue(target.is_file(), f"{target} must exist for the documented command")
            check = [interp, "-m", "py_compile", str(target)] if interp == "python3" else [interp, "--check", str(target)]
            self.assertEqual(subprocess.run(check, capture_output=True).returncode, 0, f"{rel} must load under {interp}")
        self.assertNotIn("Run `donectl.py status`", self.view)

    def test_core_carries_no_operating_layer(self):
        # The firing line, ledger, Hygiene and law/horizon references ship in their own PR.
        for word in ("spm_ledger", "Hygiene", "firing-line.md", "law-and-memory.md", "horizon.md"):
            self.assertNotIn(word, self.md, word)

    def test_within_size_cap(self):
        self.assertLessEqual(len(self.md.splitlines()), 200)

    def test_normative_text_matches_the_contract_lock(self):
        p = subprocess.run([sys.executable, str(HERE / "contract_lock.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_the_lock_catches_a_changed_an_added_and_a_removed_file(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "spm"
            shutil.copytree(HERE.parent, root)
            (root / "SKILL.md").write_text((root / "SKILL.md").read_text() + "\nchanged\n")
            (root / "references" / "zz-new.md").write_text("new rule\n")
            sorted((root / "references").glob("*.md"))[0].unlink()
            p = subprocess.run([sys.executable, str(HERE / "contract_lock.py"), "--root", str(root)],
                               capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stdout)
        for want in ("changed without re-locking: SKILL.md", "new normative file not in the lock: references/zz-new.md",
                     "locked file removed: references/"):
            self.assertIn(want, p.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
