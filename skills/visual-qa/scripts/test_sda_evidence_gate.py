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


def make_png(width, height):
    """Produce an actual small valid 8-bit RGB PNG, not arbitrary bytes."""
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload +
                struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))
    head = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scan = (b"\0" + b"\0" * (width * 3)) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) +
            chunk(b"IDAT", zlib.compress(scan, 7)) + chunk(b"IEND", b""))


class GateFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise RuntimeError("FFmpeg and ffprobe required to validate release master evidence")
        cls.media_tmp = tempfile.TemporaryDirectory()
        master = Path(cls.media_tmp.name) / "master.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
             "-f", "lavfi", "-i", "color=c=black:s=32x18:r=1:d=60",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=60",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt",
             "yuv420p", "-c:a", "aac", "-b:a", "64k",
             "-shortest", "-y", str(master)],
            check=True, timeout=35
        )
        cls.master_bytes = master.read_bytes()
        cls.master_frames = {}
        for second in [0, 5, 10, 15, 20, 30, 45, 55, 59]:
            frame = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-ss", str(second),
                 "-i", str(master), "-frames:v", "1", "-f", "image2pipe",
                 "-c:v", "png", "pipe:1"],
                capture_output=True, check=True, timeout=35,
            )
            cls.master_frames[second] = frame.stdout

    @classmethod
    def tearDownClass(cls):
        cls.media_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "writable_ancestor" / "candidate"
        self.root.mkdir(parents=True)
        self.trusted = Path(self.tmp.name) / "frozen-prior-approval.json"
        self.scope = Path(self.tmp.name) / "independent-technical-scope.json"
        self.scope.write_text(json.dumps({
            "expected_pages": ["card"], "scope_owner": "test fixture only",
            "scoped_at": "fixture",
        }))
        self.shots = {}
        self.audits = []
        for viewport, (width, height) in VIEWPORTS.items():
            shot = "card_" + viewport + ".png"
            (self.root / shot).write_bytes(make_png(width, height))
            self.shots[shot] = self.hash(shot)
            self.audits.append({
                "name": "card", "label": viewport, "shot": shot,
                "status": 200, "viewport": width, "brokenImages": 0,
                "overflowing": [], "errors": [],
            })
        self.dump_audit()
        self.doc = {
            "schema_version": 1, "expected_pages": ["card"],
            "audit": {"file": "audit.json", "sha256": self.hash("audit.json")},
            "screenshots": self.shots,
        }
        self.manifest = self.root / "manifest.json"
        self.save()

    def hash(self, file):
        return hashlib.sha256((self.root / file).read_bytes()).hexdigest()

    def dump_audit(self):
        (self.root / "audit.json").write_text(json.dumps(self.audits))

    def save(self):
        self.manifest.write_text(json.dumps(self.doc))

    def reset_audit_sha(self):
        self.dump_audit()
        self.doc["audit"]["sha256"] = self.hash("audit.json")
        self.save()

    def scope_digest(self):
        """Independent test contract: all scoped screenshot and candidate hashes."""
        keys = ("schema_version", "deliverable_type", "expected_pages",
                "audit", "screenshots", "candidate_artifact", "film")
        payload = {key: self.doc.get(key) for key in keys}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def bind_scope(self):
        digest = self.scope_digest()
        for role in ("sda", "independent_challenger"):
            self.doc["reviews"][role]["scope_sha256"] = digest
        self.doc["founder_approval"]["scope_sha256"] = digest
        comparison = self.root / "comparison.json"
        record = json.loads(comparison.read_text())
        record["scope_sha256"] = digest
        comparison.write_text(json.dumps(record))
        self.doc["comparison_report"]["sha256"] = self.hash("comparison.json")
        self.save()

    def _prepare_release_assets(self):
        frames = []
        for second in [0, 5, 10, 15, 20, 30, 45, 55, 59]:
            filename = "frame_" + str(second) + ".png"
            (self.root / filename).write_bytes(self.master_frames[second])
            frames.append({"second": second, "file": filename, "sha256": self.hash(filename)})
        (self.root / "master.mp4").write_bytes(self.master_bytes)
        (self.root / "captions.srt").write_text(
            "1\n00:00:00,000 --> 00:00:05,000\nSynthetic test caption.\n",
            encoding="utf-8"
        )
        master = self.hash("master.mp4")
        (self.root / "prior.png").write_bytes(make_png(390, 844))
        baseline = self.hash("prior.png")
        (self.root / "comparison.json").write_text(json.dumps({
            "baseline_sha256": baseline, "candidate_sha256": master,
            "observations": ["Fixture-only comparison: not a real design review"],
        }))
        self.trusted.write_text(json.dumps({
            "approved_baseline_sha256": baseline,
            "approved_by": "fixture-only", "approved_at": "fixture-date",
        }))
        return frames, master, baseline

    def release_fields(self):
        frames, master, baseline = self._prepare_release_assets()
        scores = {k: v for k, v in RUBRIC.items()}
        self.doc.update({
            "deliverable_type": "film",
            "film": {"file": "master.mp4", "sha256": master, "frames": frames,
                     "expected_duration_seconds": 60, "captions_file": "captions.srt",
                     "captions_sha256": self.hash("captions.srt")},
            "reviews": {
                "sda": {"reviewer": "design-tester", "findings": ["fixture critique"], "scores": scores},
                "independent_challenger": {
                    "reviewer": "different-tester", "findings": ["separate fixture critique"], "scores": scores,
                },
            },
            "acceptance": {k: True for k in [
                "creative_direction_approved", "brand_rights_verified", "claims_verified",
                "audio_rights_verified", "caption_alignment_verified", "actual_full_playback_verified",
            ]},
            "approved_baseline": {"file": "prior.png", "sha256": baseline},
            "comparison_report": {"file": "comparison.json", "sha256": self.hash("comparison.json")},
            "founder_approval": {
                "master_sha256": master, "approver": "test-only", "approved_at": "test-only",
            },
            "iteration_count": 1,
        })
        self.bind_scope()

    def web_release_fields(self):
        self.release_fields()
        self.doc["deliverable_type"] = "web"
        self.doc["film"] = None
        digest = self.hash("card_mobile.png")
        self.doc["candidate_artifact"] = {
            "file": "card_mobile.png", "sha256": digest,
        }
        compare = self.root / "comparison.json"
        data = json.loads(compare.read_text())
        data["candidate_sha256"] = digest
        compare.write_text(json.dumps(data))
        self.doc["comparison_report"]["sha256"] = self.hash("comparison.json")
        self.doc["founder_approval"]["master_sha256"] = digest
        for field in ("audio_rights_verified", "caption_alignment_verified",
                      "actual_full_playback_verified"):
            self.doc["acceptance"].pop(field)
        self.bind_scope()
