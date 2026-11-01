"""Adversarial installer tests; real Claude settings are never used."""
import importlib.util
import json
import shlex
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "install_sda", Path(__file__).with_name("install-sda-visual-hook.py")
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.hook = self.root / "sda_visual_router.py"
        self.hook.write_text("# real hook stand-in")
        self.settings = self.root / "settings.local.json"
        # Keep every test isolated from the real user's ~/.claude settings.
        home_patch = patch.object(installer.Path, "home", return_value=self.root)
        home_patch.start()
        self.addCleanup(home_patch.stop)

    def test_registered_command_uses_validated_custom_hook_path(self):
        custom = self.root / "custom hook's router.py"
        custom.write_text("# validated custom hook")
        self.assertEqual(installer.install(self.settings, custom), "INSTALLED")
        command = json.loads(self.settings.read_text())["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        self.assertEqual(shlex.split(command)[-1], str(custom.resolve()))
        self.assertNotIn("$HOME/.claude/hooks/sda_visual_router.py", command)
        self.assertEqual(installer.install(self.settings, custom), "ALREADY INSTALLED")

    def test_default_install_uses_loaded_user_settings(self):
        real_hook = self.root / ".claude/hooks/sda_visual_router.py"
        real_hook.parent.mkdir(parents=True)
        real_hook.write_text("# installed user hook")
        with patch.object(installer.Path, "home", return_value=self.root):
            with patch("sys.argv", ["installer", "--install"]):
                self.assertEqual(installer.main(), 0)
        self.assertTrue((self.root / ".claude/settings.json").is_file())
        self.assertFalse((self.root / ".claude/settings.local.json").exists())

    def test_first_create_is_idempotent_and_hook_only(self):
        self.assertEqual(installer.install(self.settings, self.hook), "INSTALLED")
        original = self.settings.read_bytes()
        self.assertEqual(installer.install(self.settings, self.hook), "ALREADY INSTALLED")
        self.assertEqual(self.settings.read_bytes(), original)
        hooks = json.loads(original)["hooks"]
        self.assertEqual(list(hooks), ["UserPromptSubmit"])

    def test_existing_security_hooks_refused_unchanged(self):
        original = '{"hooks":{"PreToolUse":[{"matcher":"Bash"}]}}'
        self.settings.write_text(original)
        with self.assertRaises(FileExistsError):
            installer.install(self.settings, self.hook)
        self.assertEqual(self.settings.read_text(), original)

    def test_racing_writer_before_link_preserved(self):
        from os import link as real_link
        original = '{"hooks":{"PreToolUse":[{"matcher":"Write","security":true}]}}'
        def competitor(src, dst):
            Path(dst).write_text(original)
            return real_link(src, dst)
        with patch.object(installer.os, "link", side_effect=competitor):
            with self.assertRaises(FileExistsError):
                installer.install(self.settings, self.hook)
        self.assertEqual(self.settings.read_text(), original)
        self.assertEqual(list(self.root.glob(".sda-hook-*.tmp")), [])

    def test_interrupted_link_keeps_existing_settings(self):
        with patch.object(installer.os, "link", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                installer.install(self.settings, self.hook)
        self.assertFalse(self.settings.exists())
        self.assertEqual(list(self.root.glob(".sda-hook-*.tmp")), [])

    def test_existing_global_hook_means_no_duplicate_local_install(self):
        primary = self.root / "settings.json"
        primary.write_text(json.dumps({
            "hooks": {"PreToolUse": [{"matcher": "Bash"}],
                      "UserPromptSubmit": [{"hooks": [{
                          "command": "/usr/bin/env python3 " + shlex.quote(str(self.hook.resolve()))
                      }]}]}
        }))
        self.assertEqual(installer.install(self.settings, self.hook), "ALREADY INSTALLED")
        self.assertFalse(self.settings.exists())
        self.assertIn("PreToolUse", primary.read_text())

    def test_existing_global_hook_with_local_settings_keeps_both_unchanged(self):
        global_file = self.root / "settings.json"
        global_file.write_text(json.dumps({
            "hooks": {"UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "/usr/bin/env python3 " + shlex.quote(str(self.hook.resolve()))}]}
            ]}
        }))
        local_original = '{"hooks":{"PreToolUse":[{"matcher":"Bash","security":true}]}}'
        self.settings.write_text(local_original)
        global_original = global_file.read_bytes()
        self.assertEqual(installer.install(self.settings, self.hook), "ALREADY INSTALLED")
        self.assertEqual(self.settings.read_text(), local_original)
        self.assertEqual(global_file.read_bytes(), global_original)

    def test_project_local_detects_real_user_global_registration(self):
        user_settings = self.root / ".claude/settings.json"
        user_settings.parent.mkdir(parents=True, exist_ok=True)
        user_settings.write_text(json.dumps({"hooks": {"UserPromptSubmit": [
            {"hooks": [{"type": "command",
                        "command": "/usr/bin/env python3 " + shlex.quote(str(self.hook.resolve()))}]}
        ]}}))
        project_settings = self.root / "project/.claude/settings.local.json"
        project_settings.parent.mkdir(parents=True, exist_ok=True)
        project_original = '{"hooks":{"PreToolUse":[{"matcher":"Bash","security":true}]}}'
        project_settings.write_text(project_original)
        user_original = user_settings.read_bytes()
        with patch.object(installer.Path, "home", return_value=self.root):
            self.assertEqual(installer.install(project_settings, self.hook), "ALREADY INSTALLED")
        self.assertEqual(project_settings.read_text(), project_original)
        self.assertEqual(user_settings.read_bytes(), user_original)

    def test_older_global_router_is_not_mistaken_for_current_router(self):
        primary = self.root / "settings.json"
        primary.write_text(json.dumps({"hooks": {"UserPromptSubmit": [
            {"hooks": [{"type": "command",
                        "command": "/usr/bin/env python3 /tmp/obsolete/sda_visual_router.py"}]}
        ]}}))
        original = primary.read_bytes()
        with self.assertRaises(FileExistsError):
            installer.install(self.settings, self.hook)
        self.assertFalse(self.settings.exists())
        self.assertEqual(primary.read_bytes(), original)

    def test_different_existing_router_is_not_claimed_installed(self):
        self.settings.write_text(json.dumps({"hooks": {"UserPromptSubmit": [
            {"hooks": [{"type": "command",
                        "command": "/usr/bin/env python3 /tmp/other/sda_visual_router.py"}]}
        ]}}))
        original = self.settings.read_bytes()
        with self.assertRaises(FileExistsError):
            installer.install(self.settings, self.hook)
        self.assertEqual(self.settings.read_bytes(), original)

    def test_missing_hook_refuses_without_writing(self):
        with self.assertRaises(FileNotFoundError):
            installer.install(self.settings, self.root / "missing.py")
        self.assertFalse(self.settings.exists())

    def test_bad_settings_schema_refuses(self):
        self.settings.write_text("[]")
        with self.assertRaises(ValueError):
            installer.install(self.settings, self.hook)
        self.assertEqual(self.settings.read_text(), "[]")


if __name__ == "__main__":
    unittest.main()
