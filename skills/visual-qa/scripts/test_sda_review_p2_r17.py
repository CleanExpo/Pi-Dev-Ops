"""Red-first regressions from the independent exact-SHA SDA review."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from sda_evidence_gate import check
from sda_gate_media import (
    _compare_frames, _probe, _restricted_media_input,
    _select_streams, _validate_stream_timelines,
)
from sda_gate_png import png_dimensions


class ReviewedSdaP2Regressions(unittest.TestCase):
    def test_noncanonical_manifest_parent_is_rejected_before_evidence_read(self):
        with tempfile.TemporaryDirectory(prefix="sda-r17-dotdot-") as td:
            root = Path(td) / "candidate"
            (root / "nested").mkdir(parents=True)
            (root / "manifest.json").write_text(json.dumps({"schema_version": 1}))
            # These spellings resolve to the same location but must not change
            # the root used for independent baseline/scope comparisons.
            unsafe_spelling = root / "nested" / ".." / "manifest.json"
            errors = check(unsafe_spelling)
            self.assertTrue(
                any("noncanonical" in error for error in errors), errors
            )

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "real FFmpeg and FFprobe required")
    def test_exact_ffmpeg_frame_passes_with_display_rotation(self):
        with tempfile.TemporaryDirectory(prefix="sda-r17-rotation-") as td:
            base, rotated = Path(td) / "base.mp4", Path(td) / "rotated.mp4"
            subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi",
                 "-i", "color=c=black:s=32x18:r=1:d=3",
                 "-f", "lavfi", "-i",
                 "sine=frequency=440:sample_rate=48000:duration=3",
                 "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt",
                 "yuv420p", "-c:a", "aac", "-shortest", "-y", str(base)],
                check=True, capture_output=True, timeout=35,
            )
            subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error",
                 "-display_rotation:v:0", "90", "-i", str(base),
                 "-c", "copy", "-y", str(rotated)],
                check=True, capture_output=True, timeout=35,
            )
            info = _probe(rotated)
            video, audio = _select_streams(info)
            width, height, _ = _validate_stream_timelines(info, video, audio)
            exported = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-ss", "0",
                 *_restricted_media_input(rotated), "-frames:v", "1",
                 "-f", "image2pipe", "-c:v", "png", "pipe:1"],
                check=True, capture_output=True, timeout=35,
            ).stdout
            displayed = png_dimensions(exported)
            self.assertEqual(displayed, (height, width))
            errors = []
            _compare_frames(
                rotated, {0: (exported, displayed)}, {0},
                width, height, errors,
            )
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
