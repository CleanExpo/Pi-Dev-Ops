"""AC-1 red-first proof. Run from the repo root with the test interpreter.

Exports the unchanged baseline commit to a temporary folder, copies in the new route
test file, runs only the ac1 tests, and requires: exactly 26 failures (all "next"
tests, assertion failures), 0 errors, and 52 passes (the "wrong" and "current" tests).
"""
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET

BASE = "71bad315"
TEST = "tests/test_internal_secret_routes.py"
EXPECT_FAIL, EXPECT_PASS = 26, 52


def classify(report):
    failed, errored, passed, skipped = [], [], [], []
    for case in ET.parse(report).getroot().iter("testcase"):
        name = case.get("name", "")
        failure = case.find("failure")
        if case.find("error") is not None:
            errored.append(name)
        elif failure is not None:
            text = (failure.get("message") or "") + (failure.text or "")
            (failed if "assert" in text.lower() else errored).append(name)
        elif case.find("skipped") is not None:
            skipped.append(name)
        else:
            passed.append(name)
    return failed, errored, passed, skipped


def export_and_run(root, tmp):
    """Export BASE into tmp, add the new test file, run the ac01 tests. Report path or None."""
    arch = subprocess.run(["git", "archive", "--format=tar", BASE], cwd=root,
                          capture_output=True, timeout=120)
    if arch.returncode != 0:
        print("RED_FIRST_FAIL: git archive failed:", arch.stderr.decode()[:300])
        return None
    with tarfile.open(fileobj=io.BytesIO(arch.stdout)) as tar:
        tar.extractall(tmp, filter="data")
    if os.path.exists(os.path.join(tmp, "app/server/internal_secret.py")):
        print("RED_FIRST_FAIL: baseline already has the owner module")
        return None
    shutil.copy2(os.path.join(root, TEST), os.path.join(tmp, TEST))
    report = os.path.join(tmp, "red.xml")
    env = {k: v for k, v in os.environ.items()
           if k not in ("TAO_INTERNAL_WEBHOOK_SECRET_NEXT", "TAO_FLEET_READ_SECRET")}
    run = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q", "--tb=line",
         "-k", "ac01_", f"--junitxml={report}", TEST],
        cwd=tmp, capture_output=True, text=True, timeout=240, env=env)
    print(run.stdout[-3000:])
    if not os.path.isfile(report):
        print("RED_FIRST_FAIL: no test report written; stderr:", run.stderr[-600:])
        return None
    return report


def problems_in(failed, errored, passed, skipped):
    problems = []
    if errored:
        problems.append(f"{len(errored)} errors or non-assertion failures: {errored[:3]}")
    if skipped:
        problems.append(f"{len(skipped)} skipped: {skipped[:3]}")
    if len(failed) != EXPECT_FAIL:
        problems.append(f"{len(failed)} failed, expected {EXPECT_FAIL}")
    if any("next" not in n for n in failed):
        problems.append("a failing test is not a next-key test")
    if len(passed) != EXPECT_PASS:
        problems.append(f"{len(passed)} passed, expected {EXPECT_PASS}")
    if any("next" in n for n in passed):
        problems.append("a next-key test passed on the baseline")
    return problems


def main() -> int:
    root = os.getcwd()
    if not os.path.isfile(os.path.join(root, TEST)):
        print(f"RED_FIRST_FAIL: {TEST} not found in {root}")
        return 1
    tmp = tempfile.mkdtemp(prefix="ra8408-red-")
    try:
        report = export_and_run(root, tmp)
        if report is None:
            return 1
        failed, errored, passed, skipped = classify(report)
        problems = problems_in(failed, errored, passed, skipped)
        if problems:
            print("RED_FIRST_FAIL:", "; ".join(problems))
            return 1
        print(f"RED_FIRST_OK base={BASE} failed={len(failed)} passed={len(passed)} errors=0")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
