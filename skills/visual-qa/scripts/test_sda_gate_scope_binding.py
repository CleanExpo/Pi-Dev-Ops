"""Red-first release regression: reviews and approvals must bind exact scope."""
import json
import struct
import subprocess
import unittest
import zlib
from pathlib import Path

from sda_evidence_gate import check
from test_sda_evidence_gate import GateFixture


def mutate_png_metadata(path):
    original = path.read_bytes()
    assert original[-8:-4] == b"IEND"
    data = b"revised\x00different"
    kind = b"tEXt"
    crc = struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    path.write_bytes(original[:-12] + struct.pack(">I", len(data)) +
                     kind + data + crc + original[-12:])


class ScopeBindingTests(GateFixture):
    def test_unknown_critical_png_chunk_cannot_pass_real_image_gate(self):
        image = self.root / "card_mobile.png"
        raw = image.read_bytes()
        kind, payload = b"ABCD", b"unrecognised-critical"
        chunk = (struct.pack(">I", len(payload)) + kind + payload +
                 struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))
        image.write_bytes(raw[:33] + chunk + raw[33:])
        self.doc["screenshots"]["card_mobile.png"] = self.hash("card_mobile.png")
        self.save()
        self.assertIn("unsupported critical PNG chunk", str(
            check(self.manifest, scope_record=self.scope)
        ))

    def test_boolean_findings_cannot_replace_actual_critique(self):
        self.web_release_fields()
        for review in self.doc["reviews"].values():
            review["findings"] = True
        self.save()
        self.assertIn("reviewer identity and actual critique", str(
            check(self.manifest, True, self.trusted, self.scope)
        ))

    def test_changed_desktop_capture_invalidates_previous_web_approval(self):
        self.web_release_fields()
        mutate_png_metadata(self.root / "card_desktop.png")
        self.doc["screenshots"]["card_desktop.png"] = self.hash("card_desktop.png")
        self.save()
        errors = check(self.manifest, True, self.trusted, self.scope)
        self.assertIn("scope digest", str(errors))

    def test_fresh_founder_approval_cannot_reuse_old_creative_reviews(self):
        self.web_release_fields()
        mutate_png_metadata(self.root / "card_mobile.png")
        changed = self.hash("card_mobile.png")
        self.doc["screenshots"]["card_mobile.png"] = changed
        self.doc["candidate_artifact"]["sha256"] = changed
        digest = self.scope_digest()
        self.doc["founder_approval"]["master_sha256"] = changed
        self.doc["founder_approval"]["scope_sha256"] = digest
        compared = self.root / "comparison.json"
        record = json.loads(compared.read_text())
        record["candidate_sha256"] = changed
        record["scope_sha256"] = digest
        compared.write_text(json.dumps(record))
        self.doc["comparison_report"]["sha256"] = self.hash("comparison.json")
        self.save()
        errors = check(self.manifest, True, self.trusted, self.scope)
        self.assertIn("creative review scope", str(errors))

    def test_embedded_subtitles_cannot_escape_sidecar_caption_validation(self):
        self.release_fields()
        srt = self.root / "embedded.srt"
        srt.write_text(
            "1\n00:00:10,000 --> 00:00:15,000\nContradictory embedded caption.\n"
        )
        master = self.root / "master.mp4"
        muxed = self.root / "embedded_subtitle.mp4"
        subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", str(master), "-i", str(srt),
            "-map", "0:v:0", "-map", "0:a:0", "-map", "1:0",
            "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
            "-y", str(muxed),
        ], check=True, timeout=40)
        master.write_bytes(muxed.read_bytes())
        current_sha = self.hash("master.mp4")
        self.doc["film"]["sha256"] = current_sha
        self.doc["founder_approval"]["master_sha256"] = current_sha
        compared = self.root / "comparison.json"
        record = json.loads(compared.read_text())
        record["candidate_sha256"] = current_sha
        compared.write_text(json.dumps(record))
        self.bind_scope()
        errors = check(self.manifest, True, self.trusted, self.scope)
        self.assertIn("embedded subtitle", str(errors))


if __name__ == "__main__":
    unittest.main()
