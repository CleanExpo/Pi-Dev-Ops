"""Cross-platform WSL/Linux/macOS proof of SDA's descriptor-pinned evidence I/O.

Windows native Python has no O_NOFOLLOW/openat. Its authorised WSL2 Ubuntu
runtime CAN use the POSIX contract when evidence is copied to native ext4.
These tests exercise actual file descriptors; they do not use mocked opens.
Passing here is not film/creative approval or full CI acceptance.
"""
import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path

from sda_gate_core import EvidenceAssets, _pinned_root_dir, _read_held_file
from sda_evidence_gate import check


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_DIRECTORY") and os.open in os.supports_dir_fd,
    "descriptor-confined POSIX I/O requires Linux/WSL2/macOS",
)
class SecureEvidenceFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sda-secure-files-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "evidence"
        self.root.mkdir()
        (self.root / "good.bin").write_bytes(b"actual-browser-evidence")
        self.rootfd = _pinned_root_dir(self.root)
        self.addCleanup(os.close, self.rootfd)

    def test_real_evidence_bytes_and_held_inode_are_stable(self):
        payload, identity = _read_held_file(
            self.rootfd, ["good.bin"], 1024, with_identity=True
        )
        self.assertEqual(payload, b"actual-browser-evidence")
        file_stat = (self.root / "good.bin").stat()
        self.assertEqual(identity, (file_stat.st_dev, file_stat.st_ino))
        self.assertTrue(stat.S_ISREG(file_stat.st_mode))

    def test_valid_sha_passes_and_mutated_bytes_fail(self):
        digest = hashlib.sha256(b"actual-browser-evidence").hexdigest()
        errors = []
        files = EvidenceAssets(self.rootfd, errors)
        self.assertEqual(files("good.bin", digest, "chrome mobile")[1], b"actual-browser-evidence")
        (self.root / "good.bin").write_bytes(b"changed evidence")
        self.assertIsNone(files("good.bin", digest, "chrome mobile"))
        self.assertTrue(any("SHA256 mismatch" in msg for msg in errors))

    def test_root_symlink_is_rejected_before_descriptor_capture(self):
        alias = self.base / "root-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            alias_fd = _pinned_root_dir(alias)
            os.close(alias_fd)

    def test_manifest_leaf_symlink_fails_closed(self):
        manifest = self.root / "manifest.json"
        manifest.write_text('{"schema_version":1}')
        alias = self.root / "manifest-alias.json"
        alias.symlink_to(manifest)
        errors = check(alias)
        self.assertIn("manifest missing or invalid", str(errors))

    def test_manifest_root_symlink_fails_closed(self):
        manifest = self.root / "manifest.json"
        manifest.write_text('{"schema_version":1}')
        alias = self.base / "evidence-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        errors = check(alias / "manifest.json")
        self.assertIn("evidence root cannot be securely opened", str(errors))

    def test_symlinked_parent_cannot_escape_held_evidence_root(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret.bin").write_bytes(b"private")
        (self.root / "trick").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            _read_held_file(self.rootfd, ["trick", "secret.bin"], 1024)

    def test_symlinked_leaf_is_not_read_even_with_matching_digest(self):
        outside = self.base / "secret.bin"
        outside.write_bytes(b"private")
        (self.root / "alias.bin").symlink_to(outside)
        errors = []
        file = EvidenceAssets(self.rootfd, errors)
        digest = hashlib.sha256(b"private").hexdigest()
        self.assertIsNone(file("alias.bin", digest, "chrome desktop"))
        self.assertTrue(any("unreadable or escaped root" in msg for msg in errors))

    def test_oversized_file_fails_closed_before_returning_bytes(self):
        with self.assertRaisesRegex(ValueError, "exceeds cap"):
            _read_held_file(self.rootfd, ["good.bin"], 4)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_fifo_is_not_a_regular_evidence_file(self):
        pipe = self.root / "named-pipe"
        os.mkfifo(pipe)
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            _read_held_file(self.rootfd, ["named-pipe"], 1024)


if __name__ == "__main__":
    unittest.main(verbosity=2)
