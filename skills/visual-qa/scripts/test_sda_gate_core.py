"""Adversarial contract tests for SDA evidence: real PNGs, hashes and review holds."""
import hashlib
import os
import json
import shutil
import sys
import subprocess
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib
from pathlib import Path
from sda_evidence_gate import check, RUBRIC, VIEWPORTS


from test_sda_evidence_gate import GateFixture, make_png


class GateTests(GateFixture):
    def test_recoverable_decode_error_must_hold(self):
        # FFmpeg may return zero after a damaged packet. Stderr is still fatal.
        from sda_gate_media import _decode_master
        result = subprocess.CompletedProcess([], 0, b"", b"Invalid data found when processing input")
        with patch("sda_gate_media.subprocess.run", return_value=result) as run:
            with self.assertRaisesRegex(ValueError, "decode"):
                _decode_master(self.root / "master.mp4")
        argv = run.call_args.args[0]
        self.assertIn("-xerror", argv)
        self.assertEqual(argv[argv.index("-err_detect") + 1], "explode")

    def test_web_release_does_not_require_film_or_audio(self):
        self.web_release_fields()
        self.assertEqual(check(self.manifest, True, self.trusted, self.scope), [])

    def test_web_release_stale_artifact_approval_blocks(self):
        self.web_release_fields()
        self.doc["founder_approval"]["master_sha256"] = "f" * 64
        self.save()
        self.assertIn("exact-candidate founder approval", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_web_release_incomplete_human_approval_blocks(self):
        self.web_release_fields()
        self.doc["acceptance"]["claims_verified"] = False
        self.save()
        self.assertIn("claims_verified", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_complete_capture_passes_technical_only(self):
        self.assertEqual(check(self.manifest, scope_record=self.scope), [])
        self.assertTrue(check(self.manifest, release=True, scope_record=self.scope))

    def test_missing_tablet_blocks(self):
        self.audits = [x for x in self.audits if x["label"] != "tablet"]
        self.reset_audit_sha()
        self.assertIn("missing viewports", str(check(self.manifest, scope_record=self.scope)))

    def test_mutated_screenshot_hash_blocks(self):
        (self.root / "card_mobile.png").write_text("changed")
        self.assertIn("SHA256 mismatch", str(check(self.manifest, scope_record=self.scope)))

    def test_fake_png_bytes_rejected_even_with_matching_hash(self):
        (self.root / "card_mobile.png").write_bytes(b"not really a PNG")
        self.doc["screenshots"]["card_mobile.png"] = self.hash("card_mobile.png")
        self.save()
        self.assertIn("not a PNG", str(check(self.manifest, scope_record=self.scope)))

    def test_wrong_png_width_rejected_even_with_matching_hash(self):
        (self.root / "card_mobile.png").write_bytes(make_png(320, 844))
        self.doc["screenshots"]["card_mobile.png"] = self.hash("card_mobile.png")
        self.save()
        self.assertIn("dimensions", str(check(self.manifest, scope_record=self.scope)))

    def test_missing_image_health_fails_closed(self):
        for row in self.audits:
            for key in ("brokenImages", "overflowing", "errors"):
                row.pop(key)
        self.reset_audit_sha()
        errors = str(check(self.manifest, scope_record=self.scope))
        self.assertIn("measurement missing", errors)

    def test_console_failure_blocks(self):
        self.audits[0]["errors"] = ["HTTP 404"]
        self.reset_audit_sha()
        self.assertIn("errors nonempty", str(check(self.manifest, scope_record=self.scope)))

    def test_reused_screenshot_filename_blocks(self):
        self.audits[1]["shot"] = self.audits[0]["shot"]
        self.reset_audit_sha()
        self.assertIn("screenshot path reused through alias", str(check(self.manifest, scope_record=self.scope)))

    def test_manual_founder_approval_required(self):
        self.release_fields()
        self.doc["founder_approval"] = {}
        self.save()
        self.assertIn("founder approval", str(check(self.manifest, True, self.trusted, self.scope)))

    def test_low_visual_score_blocks(self):
        self.release_fields()
        self.doc["reviews"]["sda"]["scores"]["art_direction_originality"] = 4
        self.save()
        self.assertIn("score", str(check(self.manifest, True, self.trusted, self.scope)))

    def test_nan_visual_score_blocks(self):
        self.release_fields()
        self.doc["reviews"]["sda"]["scores"]["hierarchy"] = float("nan")
        self.save()
        self.assertIn("non-finite", str(check(self.manifest, True, self.trusted, self.scope)))

    def test_same_reviewer_is_not_independent(self):
        self.release_fields()
        self.doc["reviews"]["independent_challenger"]["reviewer"] = "design-tester"
        self.save()
        self.assertIn("independent challenger", str(check(self.manifest, True, self.trusted, self.scope)))

    def test_bogus_baseline_sha_blocks(self):
        self.release_fields()
        self.doc["approved_baseline"]["sha256"] = "bogus"
        self.save()
        self.assertIn("baseline", str(check(self.manifest, True, self.trusted, self.scope)))

    def test_bogus_comparison_sha_blocks(self):
        self.release_fields()
        self.doc["comparison_report"]["sha256"] = "bogus"
        self.save()
        self.assertIn("comparison", str(check(self.manifest, True, self.trusted, self.scope)))

    def test_separate_prior_approval_record_required(self):
        self.release_fields()
        self.assertIn("separate frozen prior", str(check(self.manifest, True, scope_record=self.scope)))

    def test_prior_approval_record_sha_mismatch_blocks(self):
        self.release_fields()
        self.trusted.write_text(json.dumps({
            "approved_baseline_sha256": "a" * 64, "approved_by": "fixture", "approved_at": "fixture",
        }))
        self.assertIn("approval record SHA", str(check(self.manifest, True, self.trusted, self.scope)))

    def test_comparison_must_bind_actual_master(self):
        self.release_fields()
        compare = self.root / "comparison.json"
        payload = json.loads(compare.read_text())
        payload["candidate_sha256"] = "a" * 64
        compare.write_text(json.dumps(payload))
        self.doc["comparison_report"]["sha256"] = self.hash("comparison.json")
        self.save()
        self.assertIn("comparison not bound", str(check(self.manifest, True, self.trusted, self.scope)))

    def test_comparison_observations_require_nonblank_text(self):
        self.web_release_fields()
        comparison = self.root / "comparison.json"
        original = json.loads(comparison.read_text())
        for observations in ([None], [False], [""], ["  "], ["Valid", None]):
            with self.subTest(observations=observations):
                record = dict(original, observations=observations)
                comparison.write_text(json.dumps(record))
                self.doc["comparison_report"]["sha256"] = self.hash("comparison.json")
                self.save()
                errors = check(self.manifest, True, self.trusted, self.scope)
                self.assertIn("visual comparison record invalid", str(errors))

    def test_fifo_manifest_returns_hold_without_blocking(self):
        # Candidate controls the filename. A FIFO must never stall the gate.
        self.manifest.unlink()
        os.mkfifo(self.manifest)
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("sda_evidence_gate.py")),
             str(self.manifest), "--scope-record", str(self.scope)],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("SDA HOLD", result.stdout)

    def test_fifo_screenshot_returns_hold_without_blocking(self):
        shot = self.root / next(iter(self.shots))
        shot.unlink()
        os.mkfifo(shot)
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("sda_evidence_gate.py")),
             str(self.manifest), "--scope-record", str(self.scope)],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("SDA HOLD", result.stdout)

    def test_skill_guidance_uses_reviewed_gate_and_scope(self):
        visual = Path(__file__).parents[1]
        docs = [visual / "SKILL.md", visual / "references/sda-commercial-acceptance.md",
                visual.parent / "design-approve/SKILL.md"]
        for doc in docs:
            body = doc.read_text(encoding="utf-8")
            self.assertNotIn("~/.claude/skills/visual-qa/scripts/sda_evidence_gate.py", body,
                             str(doc) + " uses unverified installed gate")
            self.assertIn("--scope-record", body, str(doc) + " lacks required scope")

    def test_malformed_release_objects_fail_closed_without_crash(self):
        # JSON from a candidate is untrusted, including nested object shapes.
        self.web_release_fields()
        for key in ("reviews", "founder_approval", "approved_baseline",
                    "comparison_report", "candidate_artifact", "acceptance"):
            original = self.doc[key]
            self.doc[key] = ["not-an-object"]
            self.save()
            errors = check(self.manifest, True, self.trusted, self.scope)
            self.assertTrue(errors, key)
            self.doc[key] = original
        self.release_fields()
        self.doc["film"] = ["not-an-object"]
        self.save()
        self.assertIn("film must be an object",
                      str(check(self.manifest, True, self.trusted, self.scope)))

    def test_missing_scope_record_blocks(self):
        self.assertIn("scope record required", str(check(self.manifest)))

    def test_audit_bytes_are_not_reread_after_sha(self):
        # The verified audit says "broken"; a second, unverified disk read
        # would see clean and falsely pass if an attacker raced a file write.
        self.audits[0]["brokenImages"] = 1
        self.reset_audit_sha()
        original = Path.read_bytes
        snapshot = self.root / "audit.json"
        clean = [dict(r) for r in self.audits]
        clean[0]["brokenImages"] = 0

        def race_read(path):
            actual = original(path)
            if path.resolve() == snapshot.resolve():
                snapshot.write_text(json.dumps(clean))
            return actual

        with patch.object(Path, "read_bytes", race_read):
            result = check(self.manifest, scope_record=self.scope)
        self.assertIn("broken-image", str(result))

    def test_malformed_frame_second_is_fail_closed(self):
        self.release_fields()
        self.doc["film"]["frames"][0]["second"] = ["unhashable"]
        self.save()
        self.assertIn("invalid inspection timestamp", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))
