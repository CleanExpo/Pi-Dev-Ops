from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_GATE = ROOT.parent / "pr-release-gate" / "scripts" / "pr_release_gate.py"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


gate = load("engineering_gate", ROOT / "scripts" / "engineering_gate.py")

SPEC_TEXT = "# Spec\n\nBuild the thing. Writes are serialised through a single queue.\n"
NOW = datetime.now(timezone.utc).isoformat()

# A DECIDED section must quote the spec's answering sentence; PRESCRIBED sections need not.
BODY = "\n".join(
    f"## {name}\n\n> Writes are serialised through a single queue.\n\nHolds. [VERIFIED] `src/x.ts:1`\n"
    for name in gate.CATEGORIES
)


def frontmatter(categories: dict, **overrides) -> str:
    meta = {
        "type": "engineering-requirements",
        "spec": "./spec.md",
        "spec_sha256": hashlib.sha256(SPEC_TEXT.encode()).hexdigest(),
        "reviewer": "boris",
        "reviewed_at": NOW,
        "status": "PASS",
    }
    meta.update(overrides)
    lines = ["---"]
    for key, value in meta.items():
        if value is not None:
            lines.append(f"{key}: {value}")
    lines.append("categories:")
    for name, entry in categories.items():
        pairs = ", ".join(f"{k}: {v!r}" for k, v in entry.items())
        lines.append(f"  {name}: {{{pairs}}}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + BODY


def all_decided() -> dict:
    return {name: {"state": "DECIDED", "ref": f"#{name}"} for name in gate.CATEGORIES}


class GateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "spec.md").write_text(SPEC_TEXT)
        self.artifact = self.dir / "engineering.md"

    def write(self, categories: dict, **overrides) -> Path:
        self.artifact.write_text(frontmatter(categories, **overrides))
        return self.artifact

    def assertBlocked(self, needle: str):
        with self.assertRaises(gate.Blocked) as caught:
            gate.validate(self.artifact)
        joined = " | ".join(caught.exception.failures)
        self.assertIn(needle, joined)

    # --- the happy path exists, so a BLOCK below means the check fired, not that it always fails

    def test_complete_artifact_passes(self):
        self.write(all_decided())
        gate.validate(self.artifact)

    def test_deferred_and_na_with_real_reasons_pass(self):
        categories = all_decided()
        categories["migration"] = {
            "state": "DEFERRED", "reason": "no existing rows until the pilot tenant lands"
        }
        categories["budget"] = {
            "state": "N/A", "reason": "pure validator, no request path or persisted rows"
        }
        self.write(categories)
        gate.validate(self.artifact)

    # --- fail-closed behaviour

    def test_missing_artifact_blocks(self):
        self.assertBlocked("has not been reviewed")

    def test_missing_category_blocks(self):
        categories = all_decided()
        del categories["concurrency"]
        self.write(categories)
        self.assertBlocked("`concurrency` is missing")

    def test_every_category_is_individually_required(self):
        for name in gate.CATEGORIES:
            categories = all_decided()
            del categories[name]
            self.write(categories)
            self.assertBlocked(f"`{name}` is missing")

    def test_illegal_state_blocks(self):
        categories = all_decided()
        categories["rollback"] = {"state": "PROBABLY FINE"}
        self.write(categories)
        self.assertBlocked("legal states are")

    def test_deferred_without_reason_blocks(self):
        categories = all_decided()
        categories["rollback"] = {"state": "DEFERRED"}
        self.write(categories)
        self.assertBlocked("DEFERRED without a reason")

    def test_hollow_reasons_block(self):
        for hollow in ("later", "TBD", "n/a", "small change", "trivial", "will do", "todo"):
            categories = all_decided()
            categories["observability"] = {"state": "DEFERRED", "reason": hollow}
            self.write(categories)
            self.assertBlocked("hollow reason")

    def test_short_reason_blocks(self):
        categories = all_decided()
        categories["invariants"] = {"state": "N/A", "reason": "no state"}
        self.write(categories)
        self.assertBlocked("hollow reason")

    def test_decided_without_body_section_blocks(self):
        categories = all_decided()
        categories["invariants"] = {"state": "DECIDED", "ref": "#nowhere-in-the-body"}
        self.write(categories)
        self.assertBlocked("not a heading in the body")

    def test_decided_without_ref_blocks(self):
        categories = all_decided()
        categories["budget"] = {"state": "DECIDED"}
        self.write(categories)
        self.assertBlocked("without a `ref` anchor")

    def test_prescribed_is_legal_and_needs_a_body_section(self):
        """PRESCRIBED = the reviewer supplied the answer; it still has to show its working."""
        categories = all_decided()
        categories["budget"] = {"state": "PRESCRIBED", "ref": "#budget"}
        self.write(categories)
        gate.validate(self.artifact)

    def test_prescribed_without_ref_blocks(self):
        categories = all_decided()
        categories["budget"] = {"state": "PRESCRIBED"}
        self.write(categories)
        self.assertBlocked("PRESCRIBED without a `ref` anchor")

    # --- DECIDED means the spec answered it, and that is mechanically checkable

    def test_decided_without_a_quote_blocks(self):
        """Otherwise DECIDED and PRESCRIBED are indistinguishable to the validator."""
        self.artifact.write_text(
            frontmatter(all_decided()).replace("> Writes are serialised through a single queue.\n", "")
        )
        self.assertBlocked("quotes nothing from the spec")

    def test_decided_quoting_something_the_spec_never_said_blocks(self):
        body = BODY.replace(
            "> Writes are serialised through a single queue.",
            "> Every write is idempotent and retry-safe.",
        )
        self.artifact.write_text(frontmatter(all_decided()).replace(BODY, body))
        self.assertBlocked("no quoted line appears in the spec")

    def test_prescribed_needs_no_quote(self):
        """There is nothing to quote when the reviewer is supplying the answer."""
        categories = all_decided()
        categories["budget"] = {"state": "PRESCRIBED", "ref": "#budget"}
        body = BODY.replace(
            "## budget\n\n> Writes are serialised through a single queue.",
            "## budget\n\nSupplied: 1000-row page limit. [INFERENCE] PostgREST default.",
        )
        self.artifact.write_text(frontmatter(categories).replace(BODY, body))
        gate.validate(self.artifact)

    # --- status is derived from blocking findings, never chosen

    def test_blocking_finding_forces_blocked_status(self):
        categories = all_decided()
        categories["rollback"] = {"state": "DECIDED", "ref": "#rollback", "blocking": True}
        self.write(categories, status="PASS")
        self.assertBlocked("status is derived, not chosen")

    def test_blocked_status_still_fails_the_gate(self):
        """A truthful BLOCKED is not a way to pass — it names work that must happen first."""
        categories = all_decided()
        categories["rollback"] = {"state": "DECIDED", "ref": "#rollback", "blocking": True}
        self.write(categories, status="BLOCKED")
        self.assertBlocked("blocking findings must be resolved")

    def test_status_pass_with_no_blocking_findings_is_legal(self):
        self.write(all_decided(), status="PASS")
        gate.validate(self.artifact)

    def test_claiming_blocked_with_nothing_blocking_is_rejected(self):
        self.write(all_decided(), status="BLOCKED")
        self.assertBlocked("it must be PASS")

    # --- the brief's own example strings are not answers

    def test_exemplar_reason_copied_from_the_brief_blocks(self):
        for exemplar in ("no persistent state is written", "no caller outside this module"):
            categories = all_decided()
            categories["concurrency"] = {"state": "N/A", "reason": exemplar}
            self.write(categories)
            self.assertBlocked("copied verbatim from the brief's")

    def test_unknown_category_blocks(self):
        categories = all_decided()
        categories["vibes"] = {"state": "DECIDED", "ref": "#vibes"}
        self.write(categories)
        self.assertBlocked("unknown category `vibes`")

    # --- the spec binding: evidence is worthless if it floats free of what it reviewed

    def test_stale_spec_hash_blocks(self):
        self.write(all_decided())
        (self.dir / "spec.md").write_text(SPEC_TEXT + "\nOne more requirement.\n")
        self.assertBlocked("stale")

    def test_missing_spec_hash_blocks(self):
        self.write(all_decided(), spec_sha256=None)
        self.assertBlocked("missing `spec_sha256`")

    def test_absent_spec_blocks(self):
        self.write(all_decided())
        (self.dir / "spec.md").unlink()
        self.assertBlocked("spec not found")

    # --- provenance

    def test_self_review_blocks(self):
        self.write(all_decided(), reviewer="the-author")
        self.assertBlocked("`reviewer` must be one of")

    def test_naive_timestamp_blocks(self):
        self.write(all_decided(), reviewed_at="2026-07-29T10:00:00")
        self.assertBlocked("must carry a timezone")

    def test_future_timestamp_blocks(self):
        ahead = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        self.write(all_decided(), reviewed_at=ahead)
        self.assertBlocked("in the future")

    def test_claimed_pass_does_not_override_the_check(self):
        """status: PASS in the frontmatter is a claim, not evidence."""
        categories = all_decided()
        categories["rollback"] = {"state": "DEFERRED", "reason": "later"}
        self.write(categories, status="PASS")
        self.assertBlocked("hollow reason")

    # --- malformed input

    def test_no_frontmatter_blocks(self):
        self.artifact.write_text("# Engineering\n\nLooks fine to me.\n")
        self.assertBlocked("no YAML frontmatter")

    def test_wrong_type_blocks(self):
        self.write(all_decided(), type="notes")
        self.assertBlocked("must be engineering-requirements")

    # --- CLI contract

    def test_cli_exit_codes(self):
        self.write(all_decided())
        self.assertEqual(gate.main([str(self.artifact)]), 0)
        self.assertEqual(gate.main(["--spec", str(self.dir / "spec.md")]), 0)
        self.artifact.unlink()
        self.assertEqual(gate.main([str(self.artifact)]), 1)


class BenchTests(unittest.TestCase):
    """reviewer: bench adds attribution and coverage on top of every single-reviewer rule."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "spec.md").write_text(SPEC_TEXT)
        self.artifact = self.dir / "engineering.md"

    def bench(self, seats, attribution=None, extra=None):
        cats = {}
        for i, name in enumerate(gate.CATEGORIES):
            who = (attribution or {}).get(name) or seats[i % len(seats)]
            cats[name] = {"state": "DECIDED", "ref": f"#{name}", "by": who}
        overrides = {"reviewer": "bench", "seated": "[" + ", ".join(seats) + "]"}
        overrides.update(extra or {})
        self.artifact.write_text(frontmatter(cats, **overrides))
        return self.artifact

    def assertBlocked(self, needle):
        with self.assertRaises(gate.Blocked) as caught:
            gate.validate(self.artifact)
        self.assertIn(needle, " | ".join(caught.exception.failures))

    def test_bench_artifact_passes(self):
        self.bench(["boris", "eng-failure"])
        gate.validate(self.artifact)

    def test_seat_that_contributed_nothing_blocks(self):
        """The failure that turns a bench into theatre: dispatched, ran, said nothing."""
        self.bench(["boris", "eng-failure", "eng-authz", "eng-data"],
                   attribution={c: "boris" for c in gate.CATEGORIES})
        self.assertBlocked("contributed nothing")

    def test_cross_cutting_seat_may_declare_contribution_instead(self):
        """eng-secrets owns no category, so it declares what it contributed to."""
        self.bench(["boris", "eng-secrets"],
                   attribution={c: "boris" for c in gate.CATEGORIES},
                   extra={"contributed": "[eng-secrets]"})
        gate.validate(self.artifact)

    def test_category_without_attribution_blocks(self):
        cats = {c: {"state": "DECIDED", "ref": f"#{c}"} for c in gate.CATEGORIES}
        self.artifact.write_text(frontmatter(cats, reviewer="bench", seated="[boris]"))
        self.assertBlocked("does not say which seat answered it")

    def test_attribution_to_an_unseated_seat_blocks(self):
        attribution = {c: "boris" for c in gate.CATEGORIES}
        attribution["concurrency"] = "eng-ghost"
        self.bench(["boris"], attribution=attribution)
        self.assertBlocked("not in `seated`")

    def test_contributed_naming_an_unseated_seat_blocks(self):
        self.bench(["boris"], attribution={c: "boris" for c in gate.CATEGORIES},
                   extra={"contributed": "[eng-ghost]"})
        self.assertBlocked("`contributed` names `eng-ghost`")

    def test_bench_reviewer_without_seated_blocks(self):
        cats = {c: {"state": "DECIDED", "ref": f"#{c}", "by": "boris"} for c in gate.CATEGORIES}
        self.artifact.write_text(frontmatter(cats, reviewer="bench"))
        self.assertBlocked("`seated` does not list")

    def test_seat_inventing_its_own_categories_is_rejected(self):
        """Regression: the first real eng-release run emitted six invented keys.

        It treated the ten as domains rather than questions, so having no "release" category it
        made one up. The validator caught it, but nothing had told the seat -- CONTRACT.md now
        names the ten as a closed set. This asserts the rejection stays.
        """
        invented = {
            "migration_application": {"state": "PRESCRIBED", "ref": "#a", "by": "eng-release"},
            "migration_ledger_integrity": {"state": "PRESCRIBED", "ref": "#b", "by": "eng-release"},
            "dependency_resolution_parity": {"state": "PRESCRIBED", "ref": "#c", "by": "eng-release"},
            "post_deploy_verification": {"state": "PRESCRIBED", "ref": "#d", "by": "eng-release"},
        }
        self.artifact.write_text(
            frontmatter(invented, reviewer="bench", seated="[eng-release]"))
        with self.assertRaises(gate.Blocked) as caught:
            gate.validate(self.artifact)
        joined = " | ".join(caught.exception.failures)
        for key in invented:
            self.assertIn(f"unknown category `{key}`", joined)
        # and every real category is still reported missing, so the review is not half-accepted
        self.assertIn("`data_model` is missing", joined)

    def test_seat_using_its_title_instead_of_its_name_is_rejected(self):
        """The same run emitted `by: release-environment-parity` rather than `by: eng-release`."""
        cats = {c: {"state": "DECIDED", "ref": f"#{c}", "by": "release-environment-parity"}
                for c in gate.CATEGORIES}
        self.artifact.write_text(frontmatter(cats, reviewer="bench", seated="[eng-release]"))
        self.assertBlocked("release-environment-parity")

    def test_cross_cutting_seat_over_the_cap_blocks(self):
        """The 2026-07-29 RestoreAssist run: eng-compliance claimed nine of ten categories.

        It owns no category, so "stay in your lane" could not bind it, and the contract told it
        to map every finding to whichever question it answered. Every claim was substantive --
        the defect is the missing cap, not the seat.
        """
        cats = {c: {"state": "DECIDED", "ref": f"#{c}", "by": "boris"} for c in gate.CATEGORIES}
        for c in list(gate.CATEGORIES)[:9]:
            cats[c]["by"] = "eng-compliance"
        self.artifact.write_text(frontmatter(
            cats, reviewer="bench", seated="[boris, eng-compliance]",
            contributed="[eng-compliance]"))
        self.assertBlocked("owns no category yet holds 9 of them")

    def test_cross_cutting_seat_at_the_cap_passes(self):
        """Three is deliberately enough to land the strongest findings."""
        cats = {c: {"state": "DECIDED", "ref": f"#{c}", "by": "boris"} for c in gate.CATEGORIES}
        for c in list(gate.CATEGORIES)[:3]:
            cats[c]["by"] = "eng-release"
        self.artifact.write_text(frontmatter(
            cats, reviewer="bench", seated="[boris, eng-release]",
            contributed="[eng-release]"))
        gate.validate(self.artifact)

    def test_the_cap_does_not_bind_a_seat_that_owns_categories(self):
        """eng-data legitimately owns data_model and migration; it is not in `contributed`."""
        cats = {c: {"state": "DECIDED", "ref": f"#{c}", "by": "boris"} for c in gate.CATEGORIES}
        for c in list(gate.CATEGORIES)[:5]:
            cats[c]["by"] = "eng-data"
        self.artifact.write_text(frontmatter(
            cats, reviewer="bench", seated="[boris, eng-data]"))
        gate.validate(self.artifact)

    def test_single_reviewer_artifacts_still_validate(self):
        """Backwards compatibility: pre-bench artifacts carry no attribution."""
        self.artifact.write_text(frontmatter(all_decided(), reviewer="boris"))
        gate.validate(self.artifact)


class RealSeatOutputTests(unittest.TestCase):
    """The literal frontmatter eng-release emitted on 2026-07-29, kept as a fixture.

    This is the first conformant artifact any seat produced under the closed-set contract. It is
    committed verbatim -- full reason strings, not abbreviated -- so that a future edit to
    CONTRACT.md or the validator which would have rejected real seat output fails here instead of
    in production. The prior run of the same seat, on the same repo and commit, emitted six
    invented category keys and `by: release-environment-parity`; RegressionTests covers that shape.
    """

    FRONTMATTER = """---
type: engineering-requirements
spec: ./spec.md
spec_sha256: {sha}
reviewer: bench
seated: [eng-release]
contributed: [eng-release]
reviewed_at: {now}
status: {status}
categories:
  migration:          {{state: PRESCRIBED, ref: "#the-rls-migration-is-merged-and-nothing-applies-it", by: eng-release{blocking}}}
  rollback:           {{state: PRESCRIBED, ref: "#the-rls-migration-is-merged-and-nothing-applies-it", by: eng-release{blocking}}}
  failure_modes:      {{state: PRESCRIBED, ref: "#ci-and-production-install-from-a-lockfile-that-does-not-exist", by: eng-release{blocking}}}
  test_oracle:        {{state: PRESCRIBED, ref: "#ci-and-production-install-from-a-lockfile-that-does-not-exist", by: eng-release{blocking}}}
  observability:      {{state: PRESCRIBED, ref: "#no-observation-of-the-running-system-proves-this-deploy-landed", by: eng-release{blocking}}}
  data_model:         {{state: "N/A", by: eng-release, reason: "This change adds no table, column or foreign key; its one migration toggles RLS and swaps policy bodies, so there is no row-ownership shape for a release seat to argue with."}}
  invariants:         {{state: "N/A", by: eng-release, reason: "The only invariant my seat would assert here - the set of migration files at the deployed SHA equals the set recorded as applied - has no ledger to assert against, and that absence is already filed as the blocking migration finding rather than counted twice."}}
  interface_contract: {{state: "N/A", by: eng-release, reason: "The commit does delete four HTTP routes, but a removed endpoint's effect on callers is an API-surface question, not a release-mechanics one; noted under cross_domain."}}
  concurrency:        {{state: "N/A", by: eng-release, reason: "The apply path is one operator running one script by hand against one database; the hazard here is ordering between schema and code, which is a sequence problem covered under migration, not two runners racing."}}
  budget:             {{state: DEFERRED, by: eng-release, reason: "maxDuration=60 on seven analysis routes raises the Vercel function-duration ceiling sixfold; revisit when the first invoice after this deploy arrives, or the first time two analysis routes run concurrently under real load, whichever comes first."}}
---
"""

    BODY = "\n".join(
        f"## {title}\n\nFinding body. [VERIFIED] `scripts/run-migrations.ts:93`\n"
        for title in (
            "The RLS migration is merged and nothing applies it",
            "CI and production install from a lockfile that does not exist",
            "No observation of the running system proves this deploy landed",
        )
    )

    SPEC = "# Change under review\n\nCommit 1d748d0.\n"

    def build(self, blocking: bool):
        d = Path(tempfile.mkdtemp())
        (d / "spec.md").write_text(self.SPEC)
        fm = self.FRONTMATTER.format(
            sha=hashlib.sha256(self.SPEC.encode()).hexdigest(),
            now=datetime.now(timezone.utc).isoformat(),
            status="BLOCKED" if blocking else "PASS",
            blocking=", blocking: true" if blocking else "",
        )
        artifact = d / "engineering.md"
        artifact.write_text(fm + "\n" + self.BODY)
        return artifact

    def test_real_seat_output_violates_only_the_cross_cutting_cap(self):
        """Historical record: this seat over-reached too, and the cap now says so.

        eng-release declared `contributed: [eng-release]` -- owning no category -- and then held
        five. Under the contract as it stood that was legal; under the cap added after the
        RestoreAssist run it is not. Every other structural rule still passes, so the assertion
        is that the cap is the ONLY complaint. Keeping the artifact verbatim rather than trimming
        it to fit means a future change to the cap has to confront what a real seat actually did.
        """
        with self.assertRaises(gate.Blocked) as caught:
            gate.validate(self.build(blocking=False))
        failures = caught.exception.failures
        self.assertEqual(len(failures), 1, f"expected only the cap to fail, got {failures}")
        self.assertIn("owns no category yet holds 5 of them", failures[0])

    def test_real_seat_output_blocks_on_its_own_findings(self):
        """As emitted, five blocking findings must stop the build -- the gate doing its job."""
        artifact = self.build(blocking=True)
        with self.assertRaises(gate.Blocked) as caught:
            gate.validate(artifact)
        joined = " | ".join(caught.exception.failures)
        self.assertIn("blocking findings must be resolved", joined)
        for category in ("migration", "rollback", "failure_modes", "test_oracle", "observability"):
            self.assertIn(f"`{category}`", joined)
        # and nothing structural is among the complaints
        for structural in ("unknown category", "does not say which seat", "not in `seated`",
                           "hollow reason", "is missing"):
            self.assertNotIn(structural, joined)


@unittest.skipUnless(RELEASE_GATE.exists(), "pr-release-gate not installed")
class ReleaseBackstopTests(unittest.TestCase):
    """The push-time backstop, scoped to the branch diff: new specs only, no retro-fit."""

    def setUp(self):
        self.release = load("pr_release_gate", RELEASE_GATE)
        self.root = Path(tempfile.mkdtemp()).resolve()
        for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"),
                     ("config", "user.name", "t")):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)
        (self.root / "README.md").write_text("hello\n")
        self.commit("README.md")

    def commit(self, *paths: str):
        subprocess.run(["git", "add", *paths], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "x"], cwd=self.root, check=True, capture_output=True)

    def branch(self, name: str = "feature"):
        subprocess.run(["git", "checkout", "-q", "-b", name], cwd=self.root, check=True,
                       capture_output=True)

    def check(self):
        self.release.check_engineering_requirements(self.root, "main", "HEAD")

    def test_branch_touching_no_spec_is_inert(self):
        self.branch()
        (self.root / "app.ts").write_text("export const x = 1\n")
        self.commit("app.ts")
        self.check()

    def test_pre_existing_spec_is_not_retrofitted(self):
        """A spec that predates the gate and is untouched by this branch must not block."""
        (self.root / "spec.md").write_text(SPEC_TEXT)
        self.commit("spec.md")
        self.branch()
        (self.root / "app.ts").write_text("export const x = 1\n")
        self.commit("app.ts")
        self.check()

    def test_new_spec_without_engineering_md_blocks(self):
        self.branch()
        (self.root / "spec.md").write_text(SPEC_TEXT)
        self.commit("spec.md")
        with self.assertRaises(ValueError) as caught:
            self.check()
        self.assertIn("engineering requirements not satisfied", str(caught.exception))

    def test_editing_an_old_spec_pulls_it_back_into_scope(self):
        (self.root / "spec.md").write_text(SPEC_TEXT)
        self.commit("spec.md")
        self.branch()
        (self.root / "spec.md").write_text(SPEC_TEXT + "\nOne more requirement.\n")
        self.commit("spec.md")
        with self.assertRaises(ValueError):
            self.check()

    def test_new_spec_with_valid_engineering_md_passes(self):
        self.branch()
        (self.root / "spec.md").write_text(SPEC_TEXT)
        (self.root / "engineering.md").write_text(frontmatter(all_decided()))
        self.commit("spec.md", "engineering.md")
        self.check()

    def test_nested_spec_is_also_covered(self):
        self.branch()
        nested = self.root / "docs"
        nested.mkdir()
        (nested / "spec.md").write_text(SPEC_TEXT)
        self.commit("docs/spec.md")
        with self.assertRaises(ValueError) as caught:
            self.check()
        self.assertIn("docs/spec.md", str(caught.exception))


if __name__ == "__main__":
    unittest.main()


# --- positive-proof trigger conditions (deny-list -> allow-list) -------------------
# The HOLLOW_REASON deny-list only matches whole strings, so anything phrased around it
# passes. "revisit post launch" is exactly as hollow as "later" and sails through today.
# A DEFERRED/N-A reason must NAME A TESTABLE TRIGGER: a condition someone can check.

import pytest

HOLLOW_BUT_UNCAUGHT = [
    "revisit post launch",
    "later, once we scale",
    "will address in a follow-up",
    "handle this when it becomes a problem",
    "defer until we have more information",
    "not worth doing right now",
]

CONCRETE_TRIGGERS = [
    "no rows exist until the pilot tenant lands",
    "revisit before the second writer lands",
    "no measurement exists until the first bill",
    "re-open when request volume exceeds 1000/day",
    "blocked until migration 0003_orchestrator ships",
    "revisit if a second machine writes to kanban.db",
]


@pytest.mark.parametrize("reason", HOLLOW_BUT_UNCAUGHT)
def test_reason_without_a_testable_trigger_is_rejected(reason):
    """Phrasing around the deny-list must not buy a pass."""
    assert not gate.reason_names_a_trigger(reason), (
        f"{reason!r} names no checkable condition but was accepted"
    )


@pytest.mark.parametrize("reason", CONCRETE_TRIGGERS)
def test_reason_naming_a_testable_trigger_is_accepted(reason):
    """A reason that names a condition someone can check must pass."""
    assert gate.reason_names_a_trigger(reason), (
        f"{reason!r} names a checkable condition but was rejected"
    )


# --- Q2: decomposition trigger ----------------------------------------------------
# "Two rounds then decompose" is unfalsifiable prose. Make the round count structural.

def test_round_three_blocks_with_decompose_instruction():
    assert gate.decomposition_required(3) is True
    assert gate.decomposition_required(4) is True


def test_rounds_one_and_two_are_allowed():
    assert gate.decomposition_required(1) is False
    assert gate.decomposition_required(2) is False


# --- Q3: Boris must not be the diff reviewer --------------------------------------
# The release gate already requires an independent review of the DIFF. Boris reviews
# the SPEC. If the same session does both, one agent grades its own earlier opinion.

def test_same_session_reviewing_spec_and_diff_is_rejected():
    assert gate.reviewer_independence_violated("sess-abc", "sess-abc") is True


def test_different_sessions_are_fine():
    assert gate.reviewer_independence_violated("sess-abc", "sess-xyz") is False


def test_missing_diff_reviewer_is_not_a_violation():
    """Boris runs long before any diff exists — absence is normal, not a breach."""
    assert gate.reviewer_independence_violated("sess-abc", None) is False
    assert gate.reviewer_independence_violated("sess-abc", "") is False


# --- Q1: calibration floor --------------------------------------------------------
# A reviewer that never returns "nothing material here" carries zero information —
# the estate's precedent is 545 NO / 0 PASS across 1,635 verdicts. That collapse is
# invisible inside one artifact and only shows up ACROSS runs.

def test_reviewer_with_no_variance_across_runs_is_flagged():
    identical = [{"DECIDED": 10} for _ in range(6)]
    assert gate.calibration_collapsed(identical) is True


def test_reviewer_that_never_finds_a_category_clean_is_flagged():
    never_clean = [{"DECIDED": 7, "PRESCRIBED": 3} for _ in range(5)]
    assert gate.calibration_collapsed(never_clean) is True


def test_varied_reviewer_history_passes():
    varied = [
        {"DECIDED": 6, "N/A": 2, "DEFERRED": 2},
        {"DECIDED": 9, "N/A": 1},
        {"DECIDED": 4, "DEFERRED": 3, "N/A": 3},
        {"DECIDED": 8, "PRESCRIBED": 1, "N/A": 1},
    ]
    assert gate.calibration_collapsed(varied) is False


def test_short_history_cannot_collapse():
    """Three runs is not enough evidence to call a reviewer degenerate."""
    assert gate.calibration_collapsed([{"DECIDED": 10}] * 3) is False
