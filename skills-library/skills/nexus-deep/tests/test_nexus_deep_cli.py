"""Regression tests: advisory manifest cannot masquerade as trusted admission."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from nexus_deep_cli import head, init_task, main, status_task

POLICY = Path(__file__).resolve().parents[1] / "scripts" / "policy.json"


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=CI",
                        "-c", "user.email=ci@example.invalid", "commit",
                        "--allow-empty", "-qm", "baseline"], check=True)
        self.manifest = self.base / "manifest.json"

    def make(self, goal="Audit code", tier="T1", budget=None):
        return init_task(self.repo, goal, tier, self.manifest, budget)

    def test_01_valid_real_sha(self):
        x = self.make()
        self.assertEqual(x["git_head"], head(self.repo))

    def test_02_proposal_only(self):
        x = self.make()
        self.assertEqual(x["authorization_status"], "PROPOSAL")
        self.assertFalse(x["tier_authoritative"])

    def test_03_no_receipts_generated(self):
        self.assertEqual(self.make()["receipts_unverified"], [])

    def test_04_objective_hash_correct(self):
        import hashlib
        self.assertEqual(self.make()["objective_sha256"],
                         hashlib.sha256(b"Audit code").hexdigest())

    def test_05_empty_goal_rejected(self):
        with self.assertRaises(ValueError):
            self.make(" ")

    def test_06_bad_tier_rejected(self):
        with self.assertRaises(ValueError):
            self.make(tier="UNSAFE")

    def test_07_negative_budget_rejected(self):
        with self.assertRaises(ValueError):
            self.make(budget=-1)

    def test_08_overwrite_rejected(self):
        self.make()
        with self.assertRaises(FileExistsError):
            self.make(goal="Override")

    def test_09_nonrepo_rejected(self):
        with self.assertRaises(ValueError):
            init_task(self.base, "Test", "T1", self.manifest)

    def test_10_subfolder_rejected(self):
        sub = self.repo / "nested"
        sub.mkdir()
        with self.assertRaises(ValueError):
            init_task(sub, "Test", "T1", self.manifest)

    def test_11_status_not_pass(self):
        self.make()
        self.assertEqual(status_task(self.manifest)["decision"], "ENFORCEMENT_UNPROVEN")

    def test_12_fake_receipts_not_pass(self):
        self.make()
        data = json.loads(self.manifest.read_text())
        data["receipts_unverified"] = [{"gate": "all", "status": "PASS"}]
        self.manifest.write_text(json.dumps(data))
        self.assertEqual(status_task(self.manifest)["decision"], "ENFORCEMENT_UNPROVEN")
        self.assertEqual(status_task(self.manifest)["untrusted_receipt_count"], 1)

    def test_13_sha_drift_is_visible(self):
        self.make()
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=CI",
                        "-c", "user.email=ci@example.invalid", "commit",
                        "--allow-empty", "-qm", "next"], check=True)
        self.assertEqual(status_task(self.manifest)["sha_state"], "STALE_SHA")

    def test_14_unknown_policy_is_rejected(self):
        # Otherwise valid tiers, so only the enforcement guard can reject it.
        self.make()
        invalid = self.base / "policy.json"
        invalid.write_text(json.dumps({"enforcement": "ALLOW_ALL",
                                       "tiers": {"T1": {"required": []}}}))
        with self.assertRaisesRegex(ValueError, "unsafe policy"):
            status_task(self.manifest, invalid)

    def test_15_non_finite_budget_rejected_without_file(self):
        for bad in ("inf", "-inf", "nan"):
            code = main(["init", "--repo", str(self.repo), "--task", "Audit",
                         "--tier", "T1", f"--budget-aud={bad}", "--out", str(self.manifest)])
            self.assertEqual(code, 2, bad)
            self.assertFalse(self.manifest.exists(), bad)

    def test_16_status_is_proposal_only(self):
        self.make()
        self.assertEqual(status_task(self.manifest)["authorization_status"], "PROPOSAL")

    def test_17_malformed_policy_shape_rejected(self):
        self.make()
        invalid = self.base / "policy.json"
        for tiers in ({"T1": []},
                      {"T1": {"required": "tests"}},
                      {"T1": {"required": [{"authorization_status": "APPROVED"}]}}):
            invalid.write_text(json.dumps({"enforcement": "ADVISORY_ONLY", "tiers": tiers}))
            with self.assertRaisesRegex(ValueError, "policy", msg=tiers):
                status_task(self.manifest, invalid)


if __name__ == "__main__":
    unittest.main()
