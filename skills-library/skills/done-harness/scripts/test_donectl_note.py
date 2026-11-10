"""Control for `donectl note` (20/10/2026, harness weakness #9).

Progress timestamps typed by hand were wrong twice in one session. `note` stamps the time
and revision from the clock and git, never from the text, and must not disturb the lock.
    python3 skills/done-harness/scripts/test_donectl_note.py   (exit 1 on any failure)
"""
import json
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import donectl  # noqa: E402
from test_donectl_verify import make_repo  # noqa: E402


def test_note_stamps_clock_time_and_head_and_keeps_the_lock(repo):
    out, rc = donectl.start("prove note")
    assert rc == 0, out
    path = out["contract_path"]
    c = json.load(open(path))
    c["criteria"] = [{"id": "C1", "text": "holds", "recipe": "true"}]
    json.dump(c, open(path, "w"), indent=2)
    out, rc = donectl.lock()
    assert rc == 0, out
    before = datetime.now(timezone.utc).replace(microsecond=0)
    out, rc = donectl.note("C1 written; at 09:00 yesterday (a wrong hand-typed time)")
    assert rc == 0, out
    stamped = datetime.strptime(out["at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert before <= stamped <= datetime.now(timezone.utc), out
    assert out["head"] == donectl.identity()["head"], out
    lines = open(os.path.join(os.path.dirname(path), "notes.jsonl")).read().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["text"].startswith("C1 written"), lines
    assert donectl.status()["contract_status"] == "LOCKED"


def test_note_refuses_an_empty_text_and_a_missing_work_item(repo):
    out, rc = donectl.note("   ")
    assert rc == 2, out
    out, rc = donectl.note("no work item yet")
    assert rc == 1, out


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    home, cwd, failed = os.environ.get("HOME"), os.getcwd(), 0
    for name, fn in tests:
        tmp = tempfile.mkdtemp(prefix="donectl-note-test-")
        try:
            fn(make_repo(tmp))
            print(f"PASS {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}\n{traceback.format_exc()}")
        finally:
            os.chdir(cwd)
            if home is not None:
                os.environ["HOME"] = home
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
