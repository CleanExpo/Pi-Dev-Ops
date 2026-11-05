"""The lane supervisor against real processes, the real task XML and the real board script (UNI-3291)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

MESH = Path(__file__).resolve().parents[1] / "mesh"
sys.path.insert(0, str(MESH))
import lane_board  # noqa: E402
import lane_proc  # noqa: E402
import lane_state  # noqa: E402
import lane_supervisor as sup  # noqa: E402

windows_only = pytest.mark.skipif(os.name != "nt", reason="Task Scheduler and FILETIME start times are Windows-only")
SLEEPER = [sys.executable, "-c", "import time; time.sleep(120)"]


def _wait_gone(pid: int, started) -> None:
    deadline = time.time() + 15
    while lane_proc.alive(pid, started) is not False and time.time() < deadline:
        time.sleep(0.2)


@windows_only
def test_a_reused_pid_is_not_mistaken_for_the_lane() -> None:
    p = subprocess.Popen(SLEEPER)
    try:
        started = lane_proc.start_time(p.pid)
        assert isinstance(started, int) and started > 0
        assert lane_proc.alive(p.pid, started) is True
        assert lane_proc.alive(p.pid, started + 1) is False, "same pid, different start time = a different process"
    finally:
        p.kill()
        p.wait()
    _wait_gone(p.pid, started)
    assert lane_proc.alive(p.pid, started) is False


def test_boot_time_is_in_the_past() -> None:
    if not (os.name == "nt" or Path("/proc/uptime").exists()):
        pytest.skip("no uptime source on this OS")
    assert 0 < lane_proc.boot_epoch() < time.time()


def _real_lane(tmp_path: Path) -> tuple:
    d = tmp_path / "real-lane"
    d.mkdir()
    p = subprocess.Popen(SLEEPER)
    st = lane_state.begin(str(d), p.pid, SLEEPER, "long-step", "UNI-3291")
    return str(d), p, st


def test_kill_a_real_lane_and_one_tick_starts_it_again(tmp_path: Path) -> None:
    d, p, st = _real_lane(tmp_path)
    sent = []
    deps = sup.Deps(send=lambda ev: (sent.extend(ev) or True, lane_board.OK), reachable=lambda h: False)
    assert sup.tick(str(tmp_path), deps)["actions"] == {}, "a live lane was touched"
    p.kill()
    p.wait()
    _wait_gone(p.pid, st["pid_started"])
    s = sup.tick(str(tmp_path), deps)
    new = lane_state.load(d)
    try:
        assert s["actions"] == {"real-lane": "resumed"}
        assert new["pid"] != p.pid and lane_proc.alive(new["pid"], new["pid_started"]) is not False
        assert [e["action"] for e in sent] == ["resumed"]
        assert sup.tick(str(tmp_path), deps)["actions"] == {}, "the relaunched lane must now read as live"
    finally:
        subprocess.run(["taskkill", "/PID", str(new["pid"]), "/F"] if os.name == "nt" else ["kill", str(new["pid"])],
                       capture_output=True)


@windows_only
def test_the_task_runs_at_logon_and_every_five_minutes_without_elevation() -> None:
    out = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                          str(MESH / "windows" / "register_lane_supervisor.ps1"), "-PrintXml",
                          "-Python", sys.executable], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    xml = out.stdout.strip().replace('encoding="UTF-16"', "")
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    root = ET.fromstring(xml)
    assert root.find("t:Triggers/t:LogonTrigger", ns) is not None
    assert root.find("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval", ns).text == "PT5M"
    assert root.find("t:Principals/t:Principal/t:LogonType", ns).text == "InteractiveToken"
    assert root.find("t:Principals/t:Principal/t:RunLevel", ns).text == "LeastPrivilege"
    assert root.find("t:Settings/t:MultipleInstancesPolicy", ns).text == "IgnoreNew"
    args = root.find("t:Actions/t:Exec/t:Arguments", ns).text
    assert "lane_supervisor.py" in args and " tick --root " in args
    assert "Password" not in xml


@pytest.mark.skipif(os.name == "nt" or not shutil.which("python3"), reason="the board script runs on the Mini (POSIX flock)")
def test_the_board_script_writes_one_row_per_lane_and_ignores_a_resend(tmp_path: Path) -> None:
    board = tmp_path / "jobs.json"
    board.write_text(json.dumps({"jobs": [{"id": "OTHER", "status": "todo"}]}), encoding="utf-8")
    st = {"lane": "uni-1-x", "step": "receipt", "linear_id": "UNI-1", "steps_done": [], "attempts": 1,
          "resume": {"cwd": "C:/agent-work/uni-1-x"}, "host": "PC"}
    first, again = lane_board.board_event(st, "resumed", 1.0), lane_board.board_event(st, "handed_off", 1.0, "Mini")
    env = dict(os.environ, LANE_BOARD=str(board))
    for events in ([first], [first], [again]):
        r = subprocess.run(["python3", "-"], input=lane_board.remote_script(events), text=True,
                           capture_output=True, env=env)
        assert r.returncode == 0 and lane_board.OK in r.stdout, r.stderr
    jobs = json.loads(board.read_text(encoding="utf-8"))["jobs"]
    assert [j["id"] for j in jobs] == ["OTHER", "PC-LANE-UNI-1-X"]
    row = jobs[1]
    assert row["status"] == "todo" and row["assigned_to"] == "Mini" and row["linear"] == "UNI-1"
    assert row["title"] == "PC lane uni-1-x (UNI-1) stopped at step receipt: handed to Mini"
    assert len(row["event_uids"]) == 2
    assert len(list((tmp_path / ".board-bak").iterdir())) == 2, "an ignored resend must not rewrite the board"
