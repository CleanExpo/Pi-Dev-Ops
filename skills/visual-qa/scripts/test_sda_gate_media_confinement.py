"""Prevent untrusted film evidence from escaping its pinned MP4 snapshot."""
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from sda_gate_media import (
    _compare_frames, _decode_master, _inspect_master, _probe,
    _validate_stream_timelines,
)


class MediaConfinementTests(unittest.TestCase):
    def assert_restricted(self, argv):
        # Never permit FFmpeg/FFprobe to auto-detect HLS/concat/network formats.
        self.assertEqual(argv[argv.index("-f") + 1], "mov")
        self.assertEqual(argv[argv.index("-protocol_whitelist") + 1], "file")
        self.assertEqual(argv[argv.index("-enable_drefs") + 1], "0")
        self.assertEqual(argv[argv.index("-use_absolute_path") + 1], "0")
        self.assertIn("-i", argv)

    def test_ffprobe_forces_constrained_mov_demuxer(self):
        response = subprocess.CompletedProcess(
            [], 0, '{"streams":[],"format":{"duration":"60"}}', ""
        )
        with patch("sda_gate_media.subprocess.run", return_value=response) as process:
            _probe(Path("/tmp/sda-probe-verified.mp4"))
        self.assert_restricted(process.call_args.args[0])

    def test_decode_uses_same_restricted_demuxer(self):
        response = subprocess.CompletedProcess([], 0, b"", b"")
        with patch("sda_gate_media.subprocess.run", return_value=response) as process:
            _decode_master(Path("/tmp/sda-decode-verified.mp4"))
        self.assert_restricted(process.call_args.args[0])

    def test_frame_capture_uses_same_restricted_demuxer(self):
        response = subprocess.CompletedProcess([], 0, b"png-bytes", b"")
        with patch("sda_gate_media.subprocess.run", return_value=response) as process:
            errors = []
            _compare_frames(Path("/tmp/sda-frame-verified.mp4"),
                            {0: (b"png-bytes", (32, 18))},
                            {0}, 32, 18, errors)
        self.assertEqual(errors, [])
        self.assert_restricted(process.call_args.args[0])

    def test_hls_playlist_cannot_reach_ffprobe_even_with_verified_hash(self):
        # The manifest sha covers bytes, not the safety of the demuxer.
        media = b"#EXTM3U\n#EXTINF:5,\nhttp://127.0.0.1:9999/outside.ts\n"
        with patch("sda_gate_media._probe",
                   side_effect=ValueError("untrusted format was probed")) as probe:
            errors = []
            _inspect_master(("master.mp4", media),
                            {"expected_duration_seconds": 60}, None,
                            {}, set(), errors)
        self.assertIn("ISO BMFF/MP4", " ".join(errors))
        probe.assert_not_called()

    def test_aligned_but_delayed_tracks_do_not_count_as_60_second_film(self):
        info = {"format": {"duration": "90"}}
        video = {"width": 32, "height": 18, "start_time": "30",
                 "duration": "60"}
        audio = {"sample_rate": "48000", "channels": 2,
                 "start_time": "30", "duration": "60"}
        with self.assertRaisesRegex(ValueError, "container timeline|start"):
            _validate_stream_timelines(info, video, audio)


if __name__ == "__main__":
    unittest.main()
