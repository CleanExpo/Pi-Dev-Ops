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
    def test_symlink_swap_before_audit_open_cannot_escape_root(self):
        # Reproduce the exact reviewer attack: claimed hash matches
        # outside data, while the in-root file starts with decoy bytes.
        outside = Path(self.tmp.name) / "outside-audit.json"
        outside.write_text(json.dumps(self.audits))
        self.doc["audit"]["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
        self.save()
        decoy = self.root / "audit.json"
        decoy.write_text('{"decoy": true}')
        actual_open = os.open
        swapped = []

        def race_open(file, flags, *args, **kwargs):
            if file == "audit.json" and kwargs.get("dir_fd") is not None:
                decoy.unlink()
                decoy.symlink_to(outside)
                swapped.append(True)
            return actual_open(file, flags, *args, **kwargs)

        with patch.object(os, "open", side_effect=race_open):
            errors = check(self.manifest, scope_record=self.scope)
        self.assertTrue(swapped, "the controlled replacement must have occurred")
        self.assertIn("evidence file unreadable or escaped root", str(errors))

    def test_writable_ancestor_swap_cannot_escape_root(self):
        # Exact independent reviewer reproduction: manifest and expected hash
        # are self-consistent outside the original evidence root, and an
        # attacker swaps an ANCESTOR to a symlink during root open.
        outside = Path(self.tmp.name) / "attacker_copy"
        shutil.copytree(self.root.parent, outside)
        corrupted = self.root / "audit.json"
        corrupted.write_text('{"decoy":true}')
        ancestor = self.root.parent
        renamed = Path(self.tmp.name) / "previous_ancestor"
        actual_open = os.open
        swaps = []

        def race_open(file, flags, *args, **kwargs):
            if (file == "writable_ancestor" and
                    kwargs.get("dir_fd") is not None and not swaps):
                ancestor.rename(renamed)
                ancestor.symlink_to(outside, target_is_directory=True)
                swaps.append(True)
            return actual_open(file, flags, *args, **kwargs)

        with patch.object(os, "open", side_effect=race_open):
            held = check(self.manifest, scope_record=self.scope)
        self.assertTrue(swaps)
        self.assertIn("evidence root cannot be securely opened", str(held))

    def test_in_root_directory_symlink_is_rejected(self):
        outside = Path(self.tmp.name) / "external"
        outside.mkdir()
        (outside / "audit.json").write_text(json.dumps(self.audits))
        folder = self.root / "shortcut"
        folder.symlink_to(outside, target_is_directory=True)
        self.doc["audit"] = {
            "file": "shortcut/audit.json",
            "sha256": hashlib.sha256((outside / "audit.json").read_bytes()).hexdigest(),
        }
        self.save()
        self.assertIn("evidence file unreadable or escaped root", str(
            check(self.manifest, scope_record=self.scope)
        ))

    def test_candidate_cannot_reduce_approved_page_scope(self):
        self.scope.write_text(json.dumps({
            "expected_pages": ["card", "missing-portfolio"],
            "scope_owner": "fixture", "scoped_at": "fixture",
        }))
        self.assertIn("differs from independent scope", str(
            check(self.manifest, scope_record=self.scope)
        ))

    def test_alias_of_same_screenshot_cannot_be_reused(self):
        # Two distinct page names, all screenshot paths refer to the same
        # three physical images through a textual ./ prefix.
        self.scope.write_text(json.dumps({
            "expected_pages": ["card", "another"],
            "scope_owner": "fixture", "scoped_at": "fixture",
        }))
        self.doc["expected_pages"] = ["card", "another"]
        for r in list(self.audits):
            copy = dict(r, name="another", shot="./" + r["shot"])
            self.audits.append(copy)
        self.reset_audit_sha()
        for r in self.audits:
            self.doc["screenshots"][r["shot"]] = self.hash(r["shot"].removeprefix("./"))
        self.save()
        self.assertIn("reused through alias", str(
            check(self.manifest, scope_record=self.scope)
        ))

    def test_missing_audio_stream_is_a_hard_release_blocker(self):
        self.release_fields()
        silent = self.root / "silent_master.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=black:s=32x18:r=1:d=60",
             "-c:v", "libx264", "-preset", "ultrafast",
             "-pix_fmt", "yuv420p", "-y", str(silent)],
            check=True, timeout=35,
        )
        (self.root / "master.mp4").write_bytes(silent.read_bytes())
        self.doc["film"]["sha256"] = self.hash("master.mp4")
        self.save()
        self.assertIn("no actual audio stream", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_delayed_real_audio_stream_blocks_release(self):
        self.release_fields()
        input_file = self.root / "master.mp4"
        delayed = self.root / "delayed.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
             "-i", str(input_file), "-itsoffset", "0.400",
             "-i", str(input_file), "-map", "0:v:0", "-map", "1:a:0",
             "-c", "copy", "-shortest", "-y", str(delayed)],
            check=True, timeout=35,
        )
        input_file.write_bytes(delayed.read_bytes())
        self.doc["film"]["sha256"] = self.hash("master.mp4")
        self.save()
        self.assertIn("audio/video stream start offset", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_caption_timestamps_outside_master_fail(self):
        self.release_fields()
        (self.root / "captions.srt").write_text(
            "1\n00:00:58,000 --> 00:01:10,000\nOutside master.\n",
            encoding="utf-8",
        )
        self.doc["film"]["captions_sha256"] = self.hash("captions.srt")
        self.save()
        self.assertIn("caption timing overlaps or extends", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_caption_overlapping_segments_fail(self):
        self.release_fields()
        (self.root / "captions.srt").write_text(
            "1\n00:00:00,000 --> 00:00:04,000\nFirst.\n\n"
            "2\n00:00:03,800 --> 00:00:06,000\nOverlapping.\n",
            encoding="utf-8",
        )
        self.doc["film"]["captions_sha256"] = self.hash("captions.srt")
        self.save()
        self.assertIn("caption timing overlaps", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_fake_media_bytes_cannot_pass(self):
        self.release_fields()
        (self.root / "master.mp4").write_bytes(b"fake-not-an-mp4")
        self.doc["film"]["sha256"] = self.hash("master.mp4")
        self.save()
        self.assertIn("master media decode", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_fake_frame_png_cannot_pass(self):
        self.release_fields()
        (self.root / "frame_15.png").write_bytes(b"fake frame bytes")
        frame = next(x for x in self.doc["film"]["frames"] if x["second"] == 15)
        frame["sha256"] = self.hash("frame_15.png")
        self.save()
        self.assertIn("PNG cannot decode", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_frame_must_be_extracted_from_exact_master(self):
        self.release_fields()
        (self.root / "frame_15.png").write_bytes(make_png(32, 18))
        frame = next(x for x in self.doc["film"]["frames"] if x["second"] == 15)
        frame["sha256"] = self.hash("frame_15.png")
        self.save()
        self.assertIn("not actual FFmpeg master frame", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_alternate_unverified_audio_track_blocks_release(self):
        self.release_fields()
        master = self.root / "master.mp4"
        multitrack = self.root / "unverified_alternate_audio.mp4"
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", str(master), "-f", "lavfi", "-i",
            "sine=frequency=777:sample_rate=48000:duration=70",
            "-map", "0:v:0", "-map", "0:a:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "64k",
            "-y", str(multitrack),
        ], check=True, timeout=45)
        master.write_bytes(multitrack.read_bytes())
        self.doc["film"]["sha256"] = self.hash("master.mp4")
        comparison = self.root / "comparison.json"
        record = json.loads(comparison.read_text())
        record["candidate_sha256"] = self.doc["film"]["sha256"]
        comparison.write_text(json.dumps(record))
        self.doc["comparison_report"]["sha256"] = self.hash("comparison.json")
        self.doc["founder_approval"]["master_sha256"] = self.doc["film"]["sha256"]
        self.save()
        self.assertIn("multiple audio/video streams", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_malformed_nested_reviewer_returns_hold_not_traceback(self):
        self.release_fields()
        self.doc["reviews"]["sda"] = ["malformed-not-review"]
        self.save()
        self.assertIn("sda review must be an object", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_release_synthetic_fixture_passes_structurally(self):
        self.release_fields()
        self.assertEqual(check(self.manifest, True, self.trusted, self.scope), [])

    def test_four_iterations_block(self):
        self.release_fields()
        self.doc["iteration_count"] = 4
        self.save()
        self.assertIn("three", str(check(self.manifest, True, self.trusted, self.scope)))


    def test_srt_missing_separator_with_invalid_second_cue_rejected(self):
        self.release_fields()
        (self.root / "captions.srt").write_text(
            "1\n00:00:00,000 --> 00:00:05,000\nFirst.\n"
            "2\nINVALID --> INVALID\nSecond.\n", encoding="utf-8",
        )
        self.doc["film"]["captions_sha256"] = self.hash("captions.srt")
        self.save()
        result = str(check(self.manifest, True, self.trusted, self.scope))
        self.assertIn("caption cue missing blank separator", result)

    def test_hardlinked_screenshots_are_not_independent_page_evidence(self):
        self.scope.write_text(json.dumps({
            "expected_pages": ["card", "another"],
            "scope_owner": "fixture", "scoped_at": "fixture",
        }))
        self.doc["expected_pages"] = ["card", "another"]
        for row in list(self.audits):
            alias = "another_" + row["label"] + ".png"
            os.link(self.root / row["shot"], self.root / alias)
            self.doc["screenshots"][alias] = self.hash(alias)
            self.audits.append(dict(row, name="another", shot=alias))
        self.reset_audit_sha()
        self.save()
        result = str(check(self.manifest, scope_record=self.scope))
        self.assertIn("physical file reused through hard link", result)

    def test_audio_70_seconds_with_video_60_seconds_is_rejected(self):
        self.release_fields()
        input_file = self.root / "master.mp4"
        extended = self.root / "extended.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
             "-i", str(input_file),
             "-f", "lavfi", "-i",
             "sine=frequency=440:sample_rate=48000:duration=70",
             "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "64k",
             "-y", str(extended)],
            check=True, timeout=40,
        )
        input_file.write_bytes(extended.read_bytes())
        self.doc["film"]["sha256"] = self.hash("master.mp4")
        self.doc["film"]["expected_duration_seconds"] = 70
        comparison = self.root / "comparison.json"
        comparisons = json.loads(comparison.read_text())
        comparisons["candidate_sha256"] = self.doc["film"]["sha256"]
        comparison.write_text(json.dumps(comparisons))
        self.doc["comparison_report"]["sha256"] = self.hash("comparison.json")
        self.doc["founder_approval"]["master_sha256"] = self.doc["film"]["sha256"]
        self.save()
        result = str(check(self.manifest, True, self.trusted, self.scope))
        self.assertIn("audio stream ends too early/late relative to video", result)
