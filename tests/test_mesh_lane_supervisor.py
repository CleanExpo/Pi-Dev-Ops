"""lane_supervisor.py decisions, with every process and network call stood in for (UNI-3291)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mesh"))
import lane_board  # noqa: E402
import lane_state  # noqa: E402
import lane_supervisor as sup  # noqa: E402


class Fake:
    """Stand-ins for processes, ssh and the board."""

    def __init__(self, dead=(), unknown=(), reachable=(), board_ok=True, spawn_error=None):
        self.dead, self.unknown, self.ok_hosts = set(dead), set(unknown), set(reachable)
        self.board_ok, self.spawn_error = board_ok, spawn_error
        self.spawned, self.sent, self.probed, self.next_pid = [], [], [], 9000

    def alive(self, pid, started):
        return None if pid in self.unknown else pid not in self.dead

    def spawn(self, argv, cwd, env, log_path):
        if self.spawn_error:
            raise self.spawn_error
        self.next_pid += 1
        self.spawned.append({"argv": argv, "cwd": cwd, "env": env, "log": log_path, "pid": self.next_pid})
        return self.next_pid

    def reachable(self, host):
        self.probed.append(host)
        return host in self.ok_hosts

    def send(self, events):
        if not self.board_ok:
            return False, "ssh: connect to host mini port 22: Connection timed out"
        self.sent.extend(events)
        return True, lane_board.OK

    def deps(self, max_local=4):
        return sup.Deps(alive=self.alive, start_time=lambda pid: 555, spawn=self.spawn, reachable=self.reachable,
                        send=self.send, now=lambda: 1_800_000_000.0, max_local=max_local, hosts=["mini", "macbook"])


def lane(root: Path, name: str, pid: int, **kw) -> str:
    d = root / name
    d.mkdir()
    st = lane_state.new_state(str(d), pid, ["powershell.exe", "-File", str(d / "run.ps1")], "codex-review", "UNI-7")
    st.update(pid_started=111, steps_done=["clone", "tests"], **kw)
    lane_state.save(str(d), st)
    return str(d)


def state(d: str) -> dict:
    return lane_state.load(d)


def test_a_dead_running_lane_is_relaunched_from_its_last_step(tmp_path: Path) -> None:
    d = lane(tmp_path, "uni-7-job", 101)
    f = Fake(dead={101})
    s = sup.tick(str(tmp_path), f.deps())
    assert s["actions"] == {"uni-7-job": "resumed"}
    (run,) = f.spawned
    assert run["argv"] == ["powershell.exe", "-File", str(Path(d) / "run.ps1")] and run["cwd"] == d
    assert run["env"]["LANE_RESUMED"] == "1" and run["env"]["LANE_RESUME_STEP"] == "codex-review"
    assert run["env"]["LANE_STEPS_DONE"] == "clone,tests"
    st = state(d)
    assert st["state"] == "running" and st["pid"] == run["pid"] and st["pid_started"] == 555
    assert st["attempts"] == 1 and st["history"][-1]["action"] == "resumed" and st["history"][-1]["old_pid"] == 101
    (ev,) = f.sent
    assert ev["id"] == "PC-LANE-UNI-7-JOB" and ev["action"] == "resumed" and ev["linear"] == "UNI-7"
    assert ev["text"] == "PC lane uni-7-job (UNI-7) stopped at step codex-review: resumed on PC"
    assert s["board_sent"] == 1 and not s["board_pending"]


def test_live_finished_stopped_and_unknown_lanes_are_left_alone(tmp_path: Path) -> None:
    lane(tmp_path, "live", 1)
    lane(tmp_path, "finished", 2, state="done")
    stop = lane(tmp_path, "stopped", 3)
    (Path(stop) / "STOP").write_text("")
    lane(tmp_path, "cannot-tell", 4)
    f = Fake(dead={2, 3}, unknown={4})
    s = sup.tick(str(tmp_path), f.deps())
    assert s["actions"] == {} and f.spawned == [] and f.sent == []
    assert s["live"] == 2, "a lane whose process cannot be inspected must count as alive"


def test_a_busy_pc_hands_the_lane_to_the_first_reachable_mac(tmp_path: Path) -> None:
    lane(tmp_path, "a-live", 1)
    d = lane(tmp_path, "b-dead", 2)
    f = Fake(dead={2}, reachable={"macbook"})
    s = sup.tick(str(tmp_path), f.deps(max_local=1))
    assert s["actions"] == {"b-dead": "handed_off"} and f.spawned == []
    assert f.probed == ["mini", "macbook"]
    st = state(d)
    assert st["state"] == "handed_off" and st["handed_to"] == "MacBook"
    (ev,) = f.sent
    assert ev["action"] == "handed_off" and ev["target"] == "MacBook"
    assert ev["text"].endswith(": handed to MacBook") and ev["note"].startswith("Resume lane b-dead on MacBook")


def test_busy_with_no_mac_reachable_waits_and_changes_nothing(tmp_path: Path) -> None:
    lane(tmp_path, "a-live", 1)
    d = lane(tmp_path, "b-dead", 2)
    before = state(d)
    f = Fake(dead={2})
    s = sup.tick(str(tmp_path), f.deps(max_local=1))
    assert s["actions"] == {"b-dead": "waiting"} and f.sent == []
    assert state(d) == before, "a lane nobody took must stay 'running' so the next tick retries it"


def test_a_lane_that_keeps_dying_is_parked_not_restarted_forever(tmp_path: Path) -> None:
    d = lane(tmp_path, "crashy", 5, attempts=3)
    f = Fake(dead={5})
    s = sup.tick(str(tmp_path), f.deps())
    assert s["actions"] == {"crashy": "parked"} and f.spawned == []
    assert state(d)["state"] == "parked"
    (ev,) = f.sent
    assert ev["action"] == "parked" and ev["text"].endswith("relaunch limit reached after 3 relaunches")


def test_after_a_reboot_the_pc_takes_what_it_can_and_hands_off_the_rest(tmp_path: Path) -> None:
    for i, name in enumerate(["l1", "l2", "l3"]):
        lane(tmp_path, name, 100 + i)
    f = Fake(dead={100, 101, 102}, reachable={"mini"})
    s = sup.tick(str(tmp_path), f.deps(max_local=2))
    assert sorted(s["actions"].values()) == ["handed_off", "resumed", "resumed"]
    assert len(f.spawned) == 2 and len(f.sent) == 3
    assert [e["target"] for e in f.sent if e["action"] == "handed_off"] == ["Mini"]


def test_a_broken_state_file_is_reported_and_never_relaunched(tmp_path: Path) -> None:
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "lane-state.json").write_text("{half a fi", encoding="utf-8")
    (tmp_path / "no-state-lane").mkdir()
    f = Fake()
    s = sup.tick(str(tmp_path), f.deps())
    assert s["broken"] == ["broken"] and s["lanes"] == 1 and f.spawned == []


def test_an_unreachable_board_keeps_the_line_and_sends_it_once_later(tmp_path: Path) -> None:
    lane(tmp_path, "job", 7)
    f = Fake(dead={7}, board_ok=False)
    s = sup.tick(str(tmp_path), f.deps())
    assert s["actions"] == {"job": "resumed"} and s["board_pending"] and "timed out" in s["board_error"]
    assert [e["action"] for e in state(str(tmp_path / "job"))["pending_events"]] == ["resumed"]
    f.board_ok = True
    s2 = sup.tick(str(tmp_path), f.deps())
    assert s2["actions"] == {} and s2["board_sent"] == 1 and not s2["board_pending"]
    assert [e["action"] for e in f.sent] == ["resumed"]
    assert state(str(tmp_path / "job"))["pending_events"] == []
    log = (tmp_path / ".lane-supervisor" / "supervisor.log").read_text(encoding="utf-8")
    assert "board_error=" in log and "AEST" in log


def test_a_failed_relaunch_counts_as_an_attempt_and_ends_parked(tmp_path: Path) -> None:
    d = lane(tmp_path, "nobin", 8)
    f = Fake(dead={8}, spawn_error=FileNotFoundError("powershell.exe missing"))
    for _ in range(3):
        assert sup.tick(str(tmp_path), f.deps())["actions"] == {"nobin": "relaunch_failed"}
    assert state(d)["attempts"] == 3 and state(d)["history"][-1]["action"] == "relaunch_failed"
    assert sup.tick(str(tmp_path), f.deps())["actions"] == {"nobin": "parked"}


def test_a_second_tick_while_one_runs_does_nothing(tmp_path: Path) -> None:
    lane(tmp_path, "job", 9)
    f = Fake(dead={9})
    with sup.tick_lock(str(tmp_path)) as mine:
        assert mine
        assert sup.tick(str(tmp_path), f.deps()) == {"skipped": True}
    assert f.spawned == []


def test_last_tick_file_records_the_tick(tmp_path: Path) -> None:
    lane(tmp_path, "job", 10)
    sup.tick(str(tmp_path), Fake(dead={10}).deps())
    last = json.loads((tmp_path / ".lane-supervisor" / "last-tick.json").read_text(encoding="utf-8"))
    assert last["actions"] == {"job": "resumed"} and last["lanes"] == 1


@pytest.mark.parametrize("missing_root", ["does-not-exist"])
def test_a_missing_root_is_a_quiet_empty_tick(tmp_path: Path, missing_root: str) -> None:
    root = tmp_path / missing_root
    assert sup.run_tick(str(root), Fake().deps())["lanes"] == 0


def test_a_launch_whose_pid_was_never_saved_is_parked_not_started_twice(tmp_path: Path, monkeypatch) -> None:
    d = lane(tmp_path, "torn", 11)
    f = Fake(dead={11})
    real_save = sup.lane_state.save

    def save_fails_after_spawn(lane_dir, st):
        if f.spawned and st.get("pid") != 11:  # the post-spawn save that records the pid
            raise OSError("disk full")
        real_save(lane_dir, st)
    monkeypatch.setattr(sup.lane_state, "save", save_fails_after_spawn)
    assert sup.tick(str(tmp_path), f.deps())["actions"] == {"torn": "relaunch_failed"}
    monkeypatch.setattr(sup.lane_state, "save", real_save)
    st = state(d)
    assert st["launching"]["attempt"] == 1 and st["attempts"] == 1 and st["pid"] == 11
    s = sup.tick(str(tmp_path), f.deps())
    assert s["actions"] == {"torn": "parked"} and len(f.spawned) == 1, "a second copy was started"
    assert state(d)["state"] == "parked" and "never recorded" in f.sent[-1]["text"]


def test_a_child_that_registers_itself_first_keeps_its_own_record(tmp_path: Path) -> None:
    d = lane(tmp_path, "quick", 12)
    f = Fake(dead={12})
    real_spawn = f.spawn

    def spawn_and_register(argv, cwd, env, log_path):
        pid = real_spawn(argv, cwd, env, log_path)
        lane_state.begin(d, pid, argv, "codex-review", token=env["LANE_LAUNCH_TOKEN"])  # the resumed lane re-registers at once
        return pid
    f.spawn = spawn_and_register
    assert sup.tick(str(tmp_path), f.deps())["actions"] == {"quick": "resumed"}
    st = state(d)
    assert "launching" not in st and st["pid"] == 9001 and st["attempts"] == 1
    assert [e["action"] for e in f.sent] == ["resumed"]


def test_a_lane_that_restarts_during_a_handoff_is_not_handed_off(tmp_path: Path) -> None:
    lane(tmp_path, "a-live", 1)
    d = lane(tmp_path, "b-dead", 2)
    f = Fake(dead={2})
    f.reachable = lambda host: bool(lane_state.begin(d, 999, ["x"], "codex-review"))
    s = sup.tick(str(tmp_path), f.deps(max_local=1))
    assert s["actions"] == {"b-dead": "changed"} and f.sent == []
    assert state(d)["state"] == "running" and state(d)["pid"] == 999


def test_a_stale_snapshot_never_parks_a_lane_that_came_back(tmp_path: Path) -> None:
    d = lane(tmp_path, "back", 5, attempts=3)
    seen = state(d)
    lane_state.begin(d, 999, ["x"], "codex-review")  # it restarted after the scan
    f = Fake(dead={5})
    assert sup.decide(str(tmp_path), d, seen, "dead", 0, f.deps()) == ("changed", 0)
    assert state(d)["state"] == "running" and state(d)["pid"] == 999


def test_a_decision_that_cannot_be_saved_changes_nothing_and_is_made_again(tmp_path: Path, monkeypatch) -> None:
    lane(tmp_path, "a-live", 1)
    d = lane(tmp_path, "b-dead", 2)
    before = state(d)
    f = Fake(dead={2}, reachable={"mini"})
    real_save = sup.lane_state.save
    monkeypatch.setattr(sup.lane_state, "save", lambda *a: (_ for _ in ()).throw(OSError("read-only")))
    assert sup.tick(str(tmp_path), f.deps(max_local=1))["actions"] == {"b-dead": "error"}
    assert state(d) == before and f.sent == []
    monkeypatch.setattr(sup.lane_state, "save", real_save)
    assert sup.tick(str(tmp_path), f.deps(max_local=1))["actions"] == {"b-dead": "handed_off"}
    assert [e["action"] for e in f.sent] == ["handed_off"] and state(d)["pending_events"] == []


def test_a_lane_that_finished_after_the_scan_is_not_parked_or_handed_off(tmp_path: Path) -> None:
    d = lane(tmp_path, "finished-late", 6, attempts=3)
    seen = state(d)
    lane_state.update(d, state="done")  # its process is gone because it finished, not because it died
    f = Fake(dead={6}, reachable={"mini"})
    assert sup.decide(str(tmp_path), d, seen, "dead", 0, f.deps()) == ("changed", 0)
    seen2 = dict(seen, attempts=0)
    assert sup.decide(str(tmp_path), d, seen2, "dead", 9, f.deps(max_local=1)) == ("changed", 9)
    assert state(d)["state"] == "done" and f.spawned == [] and state(d)["pending_events"] == []


@pytest.fixture(autouse=True)
def process_facts(monkeypatch):
    monkeypatch.setattr(lane_state.lane_proc, "alive", lambda *a: False)
