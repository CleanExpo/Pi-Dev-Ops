#!/usr/bin/env python3
"""journal_event.py: clean events append, secret-bearing or unscanned events never land."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "journal_event.py"
fails = 0


def run(brain, *args, gitleaks=None, cwd=None, env_extra=None):
    env = dict(os.environ, SPM_BRAIN=str(brain), **(env_extra or {}))
    if gitleaks is not None:
        env["SPM_GITLEAKS"] = gitleaks
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env,
                          cwd=cwd, timeout=60)


def check(name, ok, detail=""):
    global fails
    print(f"{'OK  ' if ok else 'FAIL'} | {name}{'' if ok else ' -> ' + detail}")
    fails += not ok


def files(brain):
    return sorted((brain / "2nd Brain" / "journal").rglob("*.jsonl")) if (brain / "2nd Brain" / "journal").exists() else []


with tempfile.TemporaryDirectory() as t:
    brain = Path(t)
    (brain / "2nd Brain").mkdir()

    r = run(brain, "--summary", "clean run", "--lane", "micro", "--next", "ship it")
    got = files(brain)
    check("clean event is appended", r.returncode == 0 and len(got) == 1 and "clean run" in got[0].read_text(), r.stderr)

    before = got[0].read_text() if got else ""
    # Slack bot-token shape, not a real token. gitleaks 8.30.1 does not flag a ghp_ shape
    # inside prose (checked 22/10/2026), so that shape would make this control pass vacuously.
    fake = "xoxb-" + "123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx"
    r = run(brain, "--summary", f"deploy token {fake} used")
    after = files(brain)[0].read_text() if files(brain) else ""
    check("planted fake key is refused with exit 3", r.returncode == 3, f"rc={r.returncode} {r.stderr}")
    check("refused event writes nothing", after == before)

    r = run(brain, "--summary", "no scanner", gitleaks="/nonexistent/gitleaks")
    after2 = files(brain)[0].read_text() if files(brain) else ""
    check("missing scanner refuses with exit 4", r.returncode == 4, f"rc={r.returncode}")
    check("unscanned event writes nothing", after2 == before)

    # The repo /spm runs in must not choose the ruleset: a permissive .gitleaks.toml in the cwd,
    # and a rule-less GITLEAKS_CONFIG, each still end in a refusal.
    target = brain / "target"
    target.mkdir()
    (target / ".gitleaks.toml").write_text('[extend]\nuseDefault = true\n[allowlist]\nregexes = ["xoxb-"]\n')
    r = run(brain, "--summary", f"deploy token {fake} used", cwd=target)
    check("target repo allowlist cannot pass a secret", r.returncode == 3, f"rc={r.returncode} {r.stdout}")
    empty = brain / "empty.toml"
    empty.write_text('title = "no rules"\n')
    r = run(brain, "--summary", f"deploy token {fake} used", env_extra={"GITLEAKS_CONFIG": str(empty)})
    check("GITLEAKS_CONFIG cannot pass a secret", r.returncode == 3, f"rc={r.returncode} {r.stdout}")
    check("neither wrote anything", (files(brain)[0].read_text() if files(brain) else "") == before)

    # gitleaks skips a line holding its inline allow marker; any field could carry it.
    r = run(brain, "--summary", f"deploy token {fake} used", "--next", "document the gitleaks:allow convention")
    check("an allow marker in another field cannot pass a secret", r.returncode == 3, f"rc={r.returncode} {r.stdout}")
    check("marker attempt wrote nothing", (files(brain)[0].read_text() if files(brain) else "") == before)
    r = run(brain, "--summary", f"deploy token {fake} used # gitleaks:allow")
    check("an allow marker in the same field cannot pass a secret", r.returncode == 3, f"rc={r.returncode} {r.stdout}")
    check("same-field marker attempt wrote nothing", (files(brain)[0].read_text() if files(brain) else "") == before)

    # JSON escaping must not hide the commonest secret shape, KEY="value", in any field.
    quoted = 'api_key = "' + "Zq8vT3mK9pL2xW7nR4bY6cJ1" + '"'
    r = run(brain, "--summary", "ok", "--decision", quoted)
    check("a quoted KEY=\"value\" secret is refused", r.returncode == 3, f"rc={r.returncode} {r.stdout}")
    check("quoted secret wrote nothing", (files(brain)[0].read_text() if files(brain) else "") == before)

    # A .gitleaksignore in the repo /spm runs from must not waive findings either.
    (target / ".gitleaksignore").write_text("".join(f":generic-api-key:{i}\n" for i in range(1, 21)))
    r = run(brain, "--summary", "ok", "--decision", quoted, cwd=target)
    check("target repo .gitleaksignore cannot pass a secret", r.returncode == 3, f"rc={r.returncode} {r.stdout}")
    check(".gitleaksignore attempt wrote nothing", (files(brain)[0].read_text() if files(brain) else "") == before)

print(f"{'PASS' if not fails else 'FAIL'}: journal_event ({fails} failing)")
sys.exit(1 if fails else 0)
