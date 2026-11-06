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
from test_mesh_lane_supervisor import Fake, lane  # noqa: E402

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
    # Read-only: -PrintXml renders the scheduled task; never register or run it.
    out = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(MESH / "windows" / "register_lane_supervisor.ps1"),
            "-PrintXml",
            "-Python",
            sys.executable,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    xml = out.stdout.strip().replace('encoding="UTF-16"', "")
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    root = ET.fromstring(xml)
    assert root.find("t:Triggers/t:LogonTrigger", ns) is not None
    assert root.find("t:Triggers/t:TimeTrigger/t:Repetition/t:Interval", ns).text == "PT5M"
    assert root.find("t:Principals/t:Principal/t:LogonType", ns).text == "InteractiveToken"
    assert root.find("t:Principals/t:Principal/t:RunLevel", ns).text == "LeastPrivilege"
    assert root.find("t:Settings/t:MultipleInstancesPolicy", ns).text == "IgnoreNew"
    command = root.find("t:Actions/t:Exec/t:Command", ns).text
    args = root.find("t:Actions/t:Exec/t:Arguments", ns).text
    workdir = root.find("t:Actions/t:Exec/t:WorkingDirectory", ns).text
    script = str(MESH / "lane_supervisor.py")
    assert command == sys.executable
    assert script in args and " tick --root " in args
    assert workdir == str(MESH)
    # Negative control: a folder-only Arguments target must not satisfy this check.
    assert "lane_supervisor.py" in args
    assert not args.lstrip('"').startswith(r"C:\agent-work tick")
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


@pytest.mark.parametrize("terminal", ["parked", "handed_off"])
def test_terminal_begin_loses_board_regression(tmp_path, terminal):
    d = lane(tmp_path, "job", 123)
    f = Fake(dead={123}, reachable={"mini"}, board_ok=False)
    deps = f.deps(max_local=0)
    if terminal == "parked":
        lane_state.update(d, attempts=3)
    sup.tick(str(tmp_path), deps)
    before = lane_state.load(d)
    with pytest.raises(lane_state.StateError):
        lane_state.begin(d, 999, ["new-job"])
    assert lane_state.load(d) == before
    f.board_ok = True
    sup.tick(str(tmp_path), deps)
    assert f.sent == before["pending_events"]


@pytest.mark.parametrize("with_token", [False, True])
def test_late_child_registration_regression(tmp_path, monkeypatch, with_token):
    d = lane(tmp_path, "job", 123)
    f = Fake(dead={123}, board_ok=False)
    with monkeypatch.context() as patch:
        patch.setattr(sup, "_settle", lambda *a: (_ for _ in ()).throw(OSError("interrupted")))
        sup.tick(str(tmp_path), f.deps())
    sup.tick(str(tmp_path), f.deps())
    before = lane_state.load(d)
    assert before["state"] == "parked"
    with pytest.raises(lane_state.StateError):
        token = f.spawned[0]["env"]["LANE_LAUNCH_TOKEN"] if with_token else None
        lane_state.begin(d, f.spawned[0]["pid"], ["child"], "codex-review", token=token)
    assert lane_state.load(d) == before
    assert lane_state.run_step(d, "clone", [sys.executable, "-c", "raise SystemExit(9)"]) == 0


def test_begin_after_intent_regression(tmp_path):
    d = lane(tmp_path, "job", 123)
    f = Fake(dead={123})
    real_spawn = f.spawn
    rejected = []

    def spawn_after_begin(argv, cwd, env, log):
        try:
            lane_state.begin(d, 999, ["manual-copy"])
        except lane_state.StateError:
            rejected.append(999)
        return real_spawn(argv, cwd, env, log)
    f.spawn = spawn_after_begin
    sup.relaunch(d, lane_state.load(d), f.deps())
    assert rejected == [999] and len(f.spawned) == 1
    assert lane_state.load(d)["pid"] == f.spawned[0]["pid"]


@pytest.mark.parametrize("change", ["register", "finish", "stop", "replace"])
def test_preparation_must_keep_the_same_launch_marker(tmp_path, monkeypatch, change):
    d = lane(tmp_path, "job", 123)
    f = Fake(dead={123})
    prepare = sup._prepare_spawn

    def prep(lane_dir, st):
        args = prepare(lane_dir, st)
        if change == "register":
            lane_state.begin(d, 999, ["child"], token=args[2]["LANE_LAUNCH_TOKEN"])
        elif change == "finish":
            lane_state.update(d, state="done")
        elif change == "stop":
            (Path(d) / "STOP").touch()
        else:
            lane_state.update(d, launching=dict(st["launching"], token="replacement"))
        return args
    monkeypatch.setattr(sup, "_prepare_spawn", prep)
    assert sup.relaunch(d, lane_state.load(d), f.deps()) is None
    assert f.spawned == []


def test_child_registers_after_supervisor_settles(tmp_path, monkeypatch):
    d = lane(tmp_path, "job", 123)
    f = Fake(dead={123})
    sup.relaunch(d, lane_state.load(d), f.deps())
    child = f.spawned[0]
    token = child["env"]["LANE_LAUNCH_TOKEN"]
    monkeypatch.setattr(lane_state.lane_proc, "alive", lambda *a: True)
    st = lane_state.begin(d, child["pid"], child["argv"], token=token)
    assert st["attempts"] == 1 and st["steps_done"] == ["clone", "tests"]
    assert len(st["pending_events"]) == 1 and "launching" not in st
    with pytest.raises(lane_state.StateError):
        lane_state.begin(d, child["pid"], child["argv"], token=token)


def test_cli_child_token_and_refusal_exit_codes(tmp_path):
    d = lane(tmp_path, "job", 123)
    f = Fake(dead={123})
    sup.relaunch(d, lane_state.load(d), f.deps())
    child = f.spawned[0]
    args = [sys.executable, "-B", str(MESH / "lane_state.py"), "begin", "--dir", d,
            "--pid", str(os.getpid()), "--", "child"]
    env = dict(os.environ, LANE_LAUNCH_TOKEN=child["env"]["LANE_LAUNCH_TOKEN"])
    assert subprocess.run(args, env=env, capture_output=True).returncode == 0
    assert subprocess.run(args, env=env, capture_output=True).returncode != 0
    env.pop("LANE_LAUNCH_TOKEN")
    assert subprocess.run(args, env=env, capture_output=True).returncode != 0
