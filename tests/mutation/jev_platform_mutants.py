"""Mutation control for jev_platform: run `python tests/mutation/jev_platform_mutants.py`.

Break each guard once; the platform test suite must fail for every mutant."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
MUTANTS = [
    ("policy.py", "if not response_valid:", "if False:"),
    ("policy.py", "if state != USABLE_STATE or threshold is None:", "if threshold is None:"),
    ("policy.py", "if ABSTAIN_LOW <= noul <= ABSTAIN_HIGH:", "if False:"),
    ("policy.py", "if noul < FAIL_BELOW:", "if noul < 0.05:"),
    ("policy.py", "verdict = REFUSE if failing and not problems else ESCALATE",
     "verdict = REFUSE if failing and not problems else ('allow' if not reasons[:-1] else ESCALATE)"),
    ("policy.py", 'return "class_unverified"', 'return "class_ok"'),
    ("client.py", "if set(answers) != set(rule_ids):", "if not set(rule_ids) <= set(answers):"),
    ("client.py", "self.attempts >= self.max_attempts or ", ""),
    ("client.py", "or wait >= budget.remaining_seconds()", ""),
    ("client.py", "if len(json.dumps(body).encode()) > MAX_REQUEST_BYTES:", "if False:"),
    ("calibration.py", 'if valid_counts["v_missed"] or violations', "if violations"),
    ("calibration.py", "if record[\"bindings\"] != current_bindings:", "if False:"),
    ("calibration.py", "if cases_digest(scored) != record[\"cases_sha256\"]:", "if False:"),
    ("calibration.py", "valid = [c for c in scored if int(c[\"hash\"], 16) % 2 == 1]", "valid = scored"),
    ("engine.py", "if altered and result != policy.UNCERTAIN:", "if False:"),
    ("engine.py", "if errors or len(models) != 1:", "if len(models) > 1:"),
    ("engine.py", "if not all(p.resolve().is_relative_to(ROOT) for p in paths):", "if False:"),
    ("ask.py", "if digest != approved:", "if False:"),
    ("ask.py", "if not isinstance(approved, str):", "if False:"),
    ("ask.py", "q = _question(tid, t) if isinstance(t, dict) else None", "q = _question(tid, t or {'type': 'noul', 'question': 'x', 'true': 'y', 'false': 'z'})"),
    ("ask.py", '["git", "-C", repo, "show", f"HEAD:{MANIFEST}"]', '["cat", f"{repo}/{MANIFEST}"]'),
    ("ask.py", "nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)", "nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY, dir_fd=fd)"),
    ("ask.py", "leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)", "leaf = os.open(parts[-1], os.O_RDONLY, dir_fd=fd)"),
    ("ask.py", "    if sensitive(text):\n        return None, digest, \"sensitive content\"", "    if False:\n        return None, digest, \"sensitive content\""),
    ("ask.py", "if _DENY_NAMES.search(rel) or sensitive(rel):", "if False:"),
    ("ask.py", "if not isinstance(answers, dict) or set(answers) != set(questions):", "if not isinstance(answers, dict):"),
    ("ask.py", "if a.get(\"choice\") not in allowed or ", "if "),
    ("ask.py", "if len(set(template_ids)) != len(template_ids):", "if False:"),
]
env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
killed = 0
for fname, old, new in MUTANTS:
    path = ROOT / "jev_platform" / fname
    src = path.read_text()
    assert src.count(old) == 1, (fname, old)
    path.write_text(src.replace(old, new))
    try:
        r = subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *map(str, (ROOT / "tests").glob("test_jev_platform_*.py"))],
                           cwd=ROOT, capture_output=True, text=True, env=env)
    finally:
        path.write_text(src)
    ok = r.returncode != 0
    killed += ok
    print(("KILLED  " if ok else "SURVIVED"), fname, "|", old[:60])
print(f"{killed}/{len(MUTANTS)} mutants killed")
