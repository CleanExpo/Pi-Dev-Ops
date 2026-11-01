"""SDA hook routing tests, stdlib only, safe for GitHub CI."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
import json

MODULE = Path(__file__).with_name('sda_visual_router.py')
spec = importlib.util.spec_from_file_location('sda_visual_router', MODULE)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class RouterTests(unittest.TestCase):
    def test_design_request_emits_context(self):
        output = router.route({'prompt': 'Improve mobile UX for the Business Card'})
        self.assertEqual(output['hookSpecificOutput']['hookEventName'], 'UserPromptSubmit')
        self.assertIn('Playwright', output['hookSpecificOutput']['additionalContext'])

    def test_route_guidance_uses_current_scoped_gateway(self):
        context = router.route({'prompt': 'Review SDA UI design'})['hookSpecificOutput']['additionalContext']
        self.assertIn('skills/visual-qa/scripts/sda_evidence_gate.py', context)
        self.assertIn('--scope-record', context)
        self.assertIn('--baseline-record', context)
        self.assertNotIn('~/.claude/skills/visual-qa/scripts/sda_evidence_gate.py', context)

    def test_global_hook_requires_pinned_absolute_checkout(self):
        context = router.route({"prompt": "Review SDA UI design"})["hookSpecificOutput"]["additionalContext"]
        self.assertIn('"$PI_DEV_OPS_ROOT/skills/visual-qa/scripts/sda_evidence_gate.py"', context)
        self.assertIn('rev-parse HEAD', context)
        self.assertNotIn("python3 skills/visual-qa/scripts/sda_evidence_gate.py", context)

    def test_non_design_ignores(self):
        self.assertIsNone(router.route({'prompt': 'Check disk usage and storage'}))

    def test_missing_prompt_ignores(self):
        self.assertIsNone(router.route({}))

    def test_data_cannot_be_interpreted_as_json_commands(self):
        self.assertIsNone(router.route({'prompt': 42}))


if __name__ == '__main__':
    unittest.main()
