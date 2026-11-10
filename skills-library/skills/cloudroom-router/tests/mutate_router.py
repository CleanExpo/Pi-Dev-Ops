#!/usr/bin/env python3
"""Mutation controls for the cloudroom-router suites.

A test that has never been red is not evidence. Each mutant below reintroduces ONE defect
into a throwaway copy of the skill and asserts that the named test goes red. The source
tree is never modified. The unmutated copy must pass first, or the run is void.

Two outcomes fail the run:
  * a mutant that survives (or whose pattern no longer matches the code: stale);
  * a test that no mutant turns red, unless it is declared in NOT_KILLABLE with a reason.
So the suite cannot quietly grow tests that guard nothing.

    python3 skills/cloudroom-router/tests/mutate_router.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent

B, W = "scripts/board.py", "scripts/watchdog.py"
D, F, K = "SKILL.md", "references/worker-brief.md", "references/ticket-format.md"
TB, TW, TD = "tests/test_board.py", "tests/test_watchdog.py", "tests/test_docs.py"
SUITES = (TB, TW, TD)

# name, file, old (must appear exactly once), new, test file, test that must go red
MUTANTS = [
    # ---- board.py: validation
    ("cycle detection off", B, "    errs.extend(_cycles(graph))\n", "", TB, "test_cycle_is_found"),
    ("duplicate ids allowed", B, "        if ids.count(tid) > 1 and t is board.get(tid):\n", "        if False:\n", TB, "test_duplicate_id"),
    ("unknown dependency allowed", B, "            if d not in ids:\n", "            if False:\n", TB, "test_dependency_that_does_not_exist"),
    ("self dependency allowed", B, "            if d == tid:\n", "            if False:\n", TB, "test_self_dependency"),
    ("mode not checked", B, '        if t["mode"] not in MODES:\n', "        if False:\n", TB, "test_bad_mode_runs_and_folder_name"),
    ("valid boards rejected", B, '        if t["mode"] not in MODES:\n', "        if True:\n", TB, "test_clean_board_passes"),
    ("eval.md not required", B, 'for fname in ("prd.md", "eval.md"):', 'for fname in ("prd.md",):', TB, "test_missing_or_blank_prd_and_eval"),
    ("prd front matter not required", B, "                if fm is None:\n", "                if False:\n", TB, "test_prd_without_front_matter"),
    ("status without APPROVED is valid", B, '            if not t["approved"]:\n', "            if False:\n", TB, "test_status_without_approval_is_invalid"),
    ("status file may be several lines", B, "    if len(lines) != 1:\n", "    if False:\n", TB, "test_status_file_must_be_one_clean_line"),
    ("validate always exits 0", B, "            return 1 if errs else 0\n", "            return 0\n", TB, "test_duplicate_id"),
    ("empty tickets folder reads as clean", B, "    if not names:\n        raise BoardUnreadable", "    if False:\n        raise BoardUnreadable", TB, "test_unreadable_or_empty_tickets_folder_is_unknown_not_clean"),
    ("unreadable board exits 0", B, '    except BoardUnreadable as e:\n        print(f"UNKNOWN: {e}", file=sys.stderr)\n        return 2', '    except BoardUnreadable as e:\n        print(f"UNKNOWN: {e}", file=sys.stderr)\n        return 0', TB, "test_unreadable_or_empty_tickets_folder_is_unknown_not_clean"),

    # ---- board.py: next (reads approval and status files, never board.md)
    ("next ignores dependencies", B, "deps is not None and all(d in done for d in deps)", "deps is not None", TB, "test_only_approved_with_all_deps_done"),
    ("a ticket is ready without APPROVED", B, 't["status"] = t["state"] or ("ready" if t["approved"] else "draft")', 't["status"] = t["state"] or "ready"', TB, "test_a_draft_cannot_be_started_or_blocked_by_the_router"),
    ("next offers doing tickets", B, 't["approved"] and t["status"] == "ready" and', 't["approved"] and t["status"] in ("ready", "doing") and', TB, "test_doing_and_blocked_are_not_offered"),
    ("next reads approval from board.md", B, '"approved": (folder / APPROVED).is_file(),',
     '"approved": (folder / APPROVED).is_file() or ((root / VIEW).exists() and f"| {name.split(chr(45))[0]} |" in (root / VIEW).read_text()),',
     TB, "test_a_human_edit_to_board_md_never_changes_next"),
    ("concurrency cap ignores workers already doing", B, 'busy = sum(1 for t in board.tickets if t["status"] == "doing")', "busy = 0", TB, "test_cap_counts_workers_already_doing"),
    ("next --json ignored", B, "            if args.json:\n", "            if False:\n", TB, "test_json"),
    ("next dispatches from an invalid board", B, '        if errs:\n            for e in errs:\n                print(e, file=sys.stderr)\n            print("REFUSED: board is invalid, nothing changed or dispatched", file=sys.stderr)\n            return 1\n', "", TB, "test_invalid_board_dispatches_nothing"),
    ("set skips whole-board validation", B, '        if errs:\n            for e in errs:\n                print(e, file=sys.stderr)\n            print("REFUSED: board is invalid, nothing changed or dispatched", file=sys.stderr)\n            return 1\n', "", TB, "test_set_validates_the_whole_board_first"),

    # ---- board.py: the transition table and its conditions
    ("any move allowed", B, "    elif (old, status) not in MOVES:\n", "    elif False:\n", TB, "test_done_only_from_review_and_fix_back_keeps_the_worker"),
    ("any move allowed (table walk)", B, "    elif (old, status) not in MOVES:\n", "    elif False:\n", TB, "test_every_pair_is_decided_by_the_table_alone"),
    ("done reachable from doing", B, '("review", "done"),', '("review", "done"), ("doing", "done"),', TB, "test_done_only_from_review_and_fix_back_keeps_the_worker"),
    ("no fix-back", B, '("review", "doing"), ', "", TB, "test_done_only_from_review_and_fix_back_keeps_the_worker"),
    ("no hand-over of a lost worker", B, '("review", "done"),\n         ("doing", "doing")}', '("review", "done")}', TB, "test_reassigning_a_lost_worker_keeps_the_ticket_doing"),
    ("doing ignores unfinished dependencies", B, "        if waiting:\n", "        if False:\n", TB, "test_doing_refused_while_dependency_not_done"),
    ("doing needs no worker", B, '    if status in ("doing", "review") and not w:\n', "    if False:\n", TB, "test_doing_needs_worker"),
    ("review needs no worker", B, '    if status in ("doing", "review") and not w:\n', '    if status in ("doing",) and not w:\n', TB, "test_review_requires_a_worker_like_doing"),
    ("worker id not checked", B, "    if worker is not None and not WORKER_RE.match(worker):\n", "    if False:\n", TB, "test_bad_worker_id_refused"),
    ("a draft can be moved by the router", B, '    if old == "draft":\n', "    if False:\n", TB, "test_a_draft_cannot_be_started_or_blocked_by_the_router"),
    ("blocked forgets where it came from", B, '    return old, status, w, old if status == "blocked" else ""', '    return old, status, w, ""', TB, "test_blocked_remembers_where_it_came_from"),
    ("blocked may go anywhere", B, '        if status != t["was"]:\n', "        if False:\n", TB, "test_every_pair_is_decided_by_the_table_alone"),
    ("done can be blocked", B, "        if old not in RESUMABLE:\n", "        if False:\n", TB, "test_every_pair_is_decided_by_the_table_alone"),
    ("unknown ticket not reported", B, '        except KeyError:\n            print(f"UNKNOWN: ticket {args.id} is not on the board", file=sys.stderr)\n            return 2', "        except KeyError:\n            return 0", TB, "test_unknown_ticket_and_status"),

    # ---- board.py: APPROVED belongs to the human
    ("approve overwrites the human's marker", B, "os.O_WRONLY | os.O_CREAT | os.O_EXCL", "os.O_WRONLY | os.O_CREAT | os.O_TRUNC", TB, "test_approve_never_overwrites_the_humans_marker"),
    ("approve also writes a status", B, '    return "approved"\n', '    (matches[0] / STATUS).write_text("ready\\n")\n    return "approved"\n', TB, "test_approve_creates_only_the_marker"),
    ("approve of an unknown ticket exits 0", B, '                print(f"UNKNOWN: no single ticket folder {args.id}-* in {root}", file=sys.stderr)\n                return 2', '                return 0', TB, "test_approve_unknown_ticket"),
    ("set deletes every approval", B, '    _write_atomic(t["folder"] / STATUS, format_status(state, worker, was))\n', '    (t["folder"] / APPROVED).unlink(missing_ok=True)\n    _write_atomic(t["folder"] / STATUS, format_status(state, worker, was))\n', TB, "test_static_only_approve_creates_approved_and_nothing_deletes_it"),
    ("set creates an approval", B, '    _write_atomic(t["folder"] / STATUS, format_status(state, worker, was))\n', '    (t["folder"] / APPROVED).touch()\n    _write_atomic(t["folder"] / STATUS, format_status(state, worker, was))\n', TB, "test_no_other_command_touches_an_approval"),

    # ---- board.py: one writer per status file, and the view
    ("set rewrites every ticket's status from its own snapshot", B, "        write_status(t, state, worker, was)\n",
     '        for o in board.tickets:\n            if o["state"] or o is t:\n                write_status(o, *((state, worker, was) if o is t else (o["state"], o["worker"], o["was"])))\n',
     TB, "test_a_set_does_not_overwrite_another_tickets_status_changed_after_it_read"),
    ("set syncs approval markers from its stale snapshot", B, "        write_status(t, state, worker, was)\n",
     '        write_status(t, state, worker, was)\n        for o in board.tickets:\n            if not o["approved"]:\n                (o["folder"] / APPROVED).unlink(missing_ok=True)\n',
     TB, "test_approval_survives_a_router_write_at_every_moment"),
    ("set gives other approved tickets a status", B, "        write_status(t, state, worker, was)\n",
     '        write_status(t, state, worker, was)\n        [write_status(o, "ready", "", "") for o in board.tickets if o is not t and o["approved"] and not o["state"]]\n',
     TB, "test_dispatch_writes_only_that_tickets_status_and_the_view"),
    ("set does not regenerate the view", B, "            write_view(board)\n        except OSError as e:", "            pass\n        except OSError as e:", TB, "test_dispatch_writes_only_that_tickets_status_and_the_view"),
    ("render does not overwrite a human's edit", B, "def write_view(board: Board) -> None:\n", "def write_view(board: Board) -> None:\n    if (board.root / VIEW).exists():\n        return\n", TB, "test_render_overwrites_a_human_edit_without_reading_it"),
    ("render is not marked generated", B, '"<!-- generated by board.py render - do not edit; nothing reads this file back. "', '"<!-- "', TB, "test_render_is_a_marked_generated_view_of_the_real_state"),
    ("render shows the wrong status", B, "        status = f\"blocked (was {t['was']})\" if t[\"status\"] == \"blocked\" else t[\"status\"]\n", "        status = t[\"state\"] or \"ready\"\n", TB, "test_render_is_a_marked_generated_view_of_the_real_state"),

    # ---- board.py: atomic writes
    ("write in place instead of rename", B, "        os.replace(tmp, path)\n", "        path.write_text(data)\n        os.unlink(tmp)\n", TB, "test_the_new_content_arrives_by_rename_not_in_place"),
    ("write in place (crash case)", B, "        os.replace(tmp, path)\n", "        path.write_text(data)\n        os.unlink(tmp)\n", TB, "test_a_crash_at_the_rename_leaves_the_original_whole"),
    ("temp file left behind on failure", B, "        if os.path.exists(tmp):\n            os.unlink(tmp)\n", "        pass\n", TB, "test_a_crash_at_the_rename_leaves_the_original_whole"),
    ("write failure reported as success", B, '        print(f"UNKNOWN: could not write under {root}: {e}", file=sys.stderr)\n        return 2', '        return 0', TB, "test_a_crash_at_the_rename_leaves_the_original_whole"),

    # ---- watchdog.py: reading the tickets
    ("unreadable tickets folder reads as nothing doing", W, '        raise Unknown(f"cannot read tickets folder {tickets_dir}: {e}")', "        return {}", TW, "test_board_unreadable"),
    ("empty tickets folder accepted", W, "    if not names:\n        raise Unknown(", "    if False:\n        raise Unknown(", TW, "test_tickets_folder_without_tickets"),
    ("a status file the watchdog cannot read is skipped", W, '            raise Unknown(f"cannot read {n}/status: {e}")', "            continue", TW, "test_an_unreadable_status_file_is_unknown_not_not_doing"),
    ("an empty status file is skipped", W, '            raise Unknown(f"{n}/status is empty")', "            continue", TW, "test_an_empty_status_file_is_unknown_not_not_doing"),
    ("watchdog reads board.md as well", W, "    return doing\n",
     '    view = os.path.join(root, "board.md")\n    if os.path.exists(view):\n        for ln in open(view, encoding="utf-8"):\n            m = re.match(r"\\|\\s*(\\d+)\\s*\\|[^|]*\\|\\s*doing\\s*\\|[^|]*\\|[^|]*\\|\\s*(\\S+)\\s*\\|", ln)\n            if m:\n                doing[m.group(1)] = m.group(2)\n    return doing\n',
     TW, "test_a_generated_board_md_is_never_read"),
    ("blocked tickets counted as doing", W, '        if parts[0] == "doing":\n', '        if parts[0] == "doing" or "was=doing" in parts:\n', TW, "test_same_doing_set"),
    ("worker id taken from the wrong field", W, 'p.startswith("worker=")', 'p.startswith("was=")', TW, "test_same_doing_set"),
    ("tickets env ignored", W, 'ap.add_argument("--tickets", default=env.get("ROUTER_TICKETS", "specs/tickets"))', 'ap.add_argument("--tickets", default="specs/tickets")', TW, "test_router_and_board_from_environment"),

    # ---- watchdog.py: judging the threads
    ("router missing from list is not fatal", W, "    if router not in by_id:\n", "    if False:\n", TW, "test_router_missing_from_list_is_a_partial_read"),
    ("empty list reads as clean", W, "not isinstance(data, list) or not data", "not isinstance(data, list)", TW, "test_empty_list"),
    ("json object accepted as a list", W, "not isinstance(data, list) or not data", "not data", TW, "test_json_object_not_list"),
    ("malformed thread entry accepted", W, 'not isinstance(t, dict) or not isinstance(t.get("id"), str) or not isinstance(t.get("status"), str)', "False", TW, "test_malformed_entry"),
    ("room-cli exit status ignored", W, "        if p.returncode != 0:\n", "        if False:\n", TW, "test_room_cli_exits_nonzero"),
    ("empty room-cli output ignored", W, "    if not raw.strip():\n", "    if False:\n", TW, "test_room_cli_prints_nothing"),
    ("missing room-cli binary reported vaguely", W, "room-cli thread list failed to run", "thread list problem", TW, "test_room_cli_missing_binary"),
    ("unreadable --input reported vaguely", W, 'raise Unknown(f"cannot read --input {input_path}: {e}")', 'raise Unknown(f"bad input")', TW, "test_input_file_missing"),
    ("not-JSON reported as something else", W, 'raise Unknown(f"{source} is not JSON: {e}")', 'raise Unknown(f"{source} is odd")', TW, "test_not_json"),
    ("UNKNOWN exits 0", W, '        print(f"UNKNOWN: {e}", file=sys.stderr)\n        return 2', '        print(f"UNKNOWN: {e}", file=sys.stderr)\n        return 0', TW, "test_empty_output"),
    ("no router id accepted", W, "        if not args.router:\n", "        if False:\n", TW, "test_no_router_id"),
    ("router id env ignored", W, 'ap.add_argument("--router", default=env.get("ROUTER_THREAD_ID"))', 'ap.add_argument("--router", default=None)', TW, "test_router_and_board_from_environment"),
    ("stall env ignored", W, 'default=float(env.get("ROUTER_STALL_MIN", "20"))', "default=20.0", TW, "test_stall_boundary_and_option"),
    ("stall threshold inverted", W, "if age_min > stall_min:", "if age_min < stall_min:", TW, "test_stall_boundary_and_option"),
    ("active thread without updatedAt accepted", W, "            if age_min is None:\n", "            if False:\n", TW, "test_active_child_without_updatedat"),
    ("STALLED never raised", W, "            if age_min > stall_min:", "            if False:", TW, "test_each_condition_flags_exactly_once"),
    ("ORPHAN never raised", W, "        elif worker not in by_id:", "        elif False:", TW, "test_each_condition_flags_exactly_once"),
    ("FINISHED_UNREVIEWED never raised", W, '        elif status == "idle" and tid in ticket_of:', "        elif False:", TW, "test_each_condition_flags_exactly_once"),
    ("WAITING_HUMAN never raised", W, '        elif t.get("hasPendingInteraction"):', "        elif False:", TW, "test_each_condition_flags_exactly_once"),
    ("FAILED never raised", W, "        if status in FAILED_STATES or runtime_status in FAILED_STATES:", "        if False:", TW, "test_each_condition_flags_exactly_once"),
    ("a stalled worker outranks a waiting one", W, '        elif t.get("hasPendingInteraction"):', '        elif t.get("hasPendingInteraction") and status != "active":', TW, "test_waiting_beats_stalled"),
    ("review tickets flagged as finished", W, 'elif status == "idle" and tid in ticket_of:', 'elif status == "idle":', TW, "test_idle_child_with_ticket_review_is_not_flagged"),
    ("other parents' threads watched", W, 'children = [t for t in threads if t.get("parentThreadId") == router]', "children = list(threads)", TW, "test_children_of_other_parents_are_ignored"),
    ("clean run prints noise", W, "        for f in flags:\n            print(line(f))\n    return", '        print("all clear")\n        for f in flags:\n            print(line(f))\n    return', TW, "test_clean_is_silent_exit_zero"),
    ("--json ignored", W, "    if args.json:\n", "    if False:\n", TW, "test_json_output"),
    ("happy path through room-cli differs", W, 'raw = p.stdout\n', 'raw = ""\n', TW, "test_room_cli_happy_path_reaches_the_same_verdict"),

    # ---- watchdog.py: notify (create only, deduped, retried)
    ("flags exit 0 without --notify", W, "return 0 if (args.notify or not flags) else 1", "return 0", TW, "test_without_notify_nothing_is_sent"),
    ("notify exits 1 after delivering", W, "return 0 if (args.notify or not flags) else 1", "return 0 if not flags else 1", TW, "test_flags_are_queued_to_the_router_with_create_only"),
    ("notify default on", W, 'default=env.get("ROUTER_NOTIFY") == "1"', "default=True", TW, "test_without_notify_nothing_is_sent"),
    ("ROUTER_NOTIFY env ignored", W, 'default=env.get("ROUTER_NOTIFY") == "1"', "default=False", TW, "test_notify_from_the_environment_for_a_script_loop"),
    ("notify also sends (the 404 on an idle router)", W, '    out = _run_cli(["thread", "queue", "create", router, message, "--json"], "queue create")\n', '    out = _run_cli(["thread", "queue", "create", router, message, "--json"], "queue create")\n    _run_cli(["thread", "queue", "send", router, "qmsg_1"], "queue send")\n', TW, "test_flags_are_queued_to_the_router_with_create_only"),
    ("same flags resent every tick", W, '    if prev.get("sig") == sig and', "    if False and", TW, "test_same_flags_are_not_resent_until_the_renotify_window_passes"),
    ("renotify window never reopens", W, '(now_ms - prev["at"]) / 60000 < renotify_min', "True", TW, "test_same_flags_are_not_resent_until_the_renotify_window_passes"),
    ("flag identity includes the minutes stuck", W, "f\"{f['kind']}|{f['thread']}|{f['ticket']}\"", "f\"{f['kind']}|{f['thread']}|{f['ticket']}|{f['detail']}\"", TW, "test_same_flags_are_not_resent_until_the_renotify_window_passes"),
    ("a changed flag set waits for the window", W, "    sig = signature(flags)\n", '    sig = "fixed"\n', TW, "test_a_changed_flag_set_is_sent_at_once"),
    ("recovery keeps the state", W, "                forget(state)\n", "                pass\n", TW, "test_recovery_forgets_the_state_so_a_new_problem_is_reported"),
    ("queue create failure ignored", W, '    if p.returncode != 0:\n        raise Unknown(f"could not notify router', '    if False:\n        raise Unknown(f"could not notify router', TW, "test_queue_create_failure_is_unknown_and_is_retried_next_tick"),
    ("a reply without a message id accepted", W, '        json.loads(out)["id"]\n', "        json.loads(out)\n", TW, "test_a_create_reply_without_an_id_is_unknown"),
    ("state written before the message is queued", W, '    out = _run_cli(["thread", "queue", "create", router, message, "--json"], "queue create")\n', '    open(state_path, "w").write(json.dumps({"sig": sig, "at": now_ms}))\n    out = _run_cli(["thread", "queue", "create", router, message, "--json"], "queue create")\n', TW, "test_queue_create_failure_is_unknown_and_is_retried_next_tick"),
    ("message goes to the wrong thread", W, '["thread", "queue", "create", router, message, "--json"]', '["thread", "queue", "create", "thr_other", message, "--json"]', TW, "test_flags_are_queued_to_the_router_with_create_only"),
    ("message omits the flags", W, '    body = "\\n".join(line(f) for f in flags)', '    body = ""', TW, "test_flags_are_queued_to_the_router_with_create_only"),
    ("a clean run notifies", W, "            if flags:\n                notify(", "            if True:\n                notify(", TW, "test_clean_run_sends_nothing"),

    # ---- the prose that agents obey
    ("loop delete without --yes", D, '`room-cli loop delete <loopId> --project "$ROOM_PROJECT_ID" --yes`', '`room-cli loop delete <loopId> --project "$ROOM_PROJECT_ID"`', TD, "test_every_loop_delete_carries_yes"),
    ("worker brief allows no child threads at all", F, "Child threads: mode solo: no child threads.", "Do not start other threads or agents. mode solo: no child threads.", TD, "test_one_rule_for_worker_child_threads_in_both_files"),
    ("local spawn loses the snapshot commit", D, "  --base-branch <local snapshot SHA> \\\n", "", TD, "test_local_and_cloud_spawn_are_separate_commands_with_the_right_base"),
    ("cloud spawn passes a SHA", D, "--machine cloud --base-branch tickets/<id>", "--machine cloud --base-branch <local snapshot SHA>", TD, "test_local_and_cloud_spawn_are_separate_commands_with_the_right_base"),
    ("cloud branch is pushed some other way", D, "and push it through `pr-release-gate`", "and push it", TD, "test_local_and_cloud_spawn_are_separate_commands_with_the_right_base"),
    ("fix-back uses queue send on an idle thread", D, "b set <id> doing        # worker is kept", "room-cli thread queue send <thr> <messageId>\nb set <id> doing        # worker is kept", TD, "test_queue_create_on_an_idle_thread_delivers_so_send_is_for_busy_targets_only"),
    ("the HTTP 404 note is dropped", D, "HTTP 404", "HTTP 200", TD, "test_queue_create_on_an_idle_thread_delivers_so_send_is_for_busy_targets_only"),
    ("brief loses the absolute ticket path", F, "<ABSOLUTE TICKET FOLDER> (the router's checkout)", "the router's checkout", TD, "test_worker_brief_gives_the_absolute_ticket_path_as_fallback"),
    ("loop command mixes in agent flags", D, '  --cron "*/10 * * * *" --timezone UTC \\\n', '  --cron "*/10 * * * *" --timezone UTC --prompt hi \\\n', TD, "test_watchdog_loop_is_a_script_loop_with_no_agent_flags"),
    ("loop reads board.md", D, '\\"ROUTER_TICKETS\\":\\"$PWD/specs/tickets\\"', '\\"ROUTER_TICKETS\\":\\"$PWD/specs/tickets/board.md\\"', TD, "test_the_loop_reads_the_tickets_folder_not_board_md"),
    ("APPROVED is no longer human only", D, "HUMAN ONLY", "shared", TD, "test_one_writer_per_file_is_stated_the_same_way_everywhere"),
    ("ticket-format loses the one-writer table", K, "**the human only**", "the human", TD, "test_one_writer_per_file_is_stated_the_same_way_everywhere"),
    ("the router may run approve", D, "never runs `approve`", "may run `approve`", TD, "test_one_writer_per_file_is_stated_the_same_way_everywhere"),
    ("the two-writer text comes back", D, "## Rules that stay true", "## Rules that stay true\nTake flock on board.md before any edit.", TD, "test_nothing_still_describes_the_two_writer_design"),
    ("lock code comes back in board.py", B, "import argparse\n", "import argparse\nimport fcntl\n", TD, "test_board_py_has_no_lock_or_hash_code_left"),
    ("skill grows past 200 lines", D, "## Rules that stay true", "\n" * 200 + "## Rules that stay true", TD, "test_skill_is_short_enough_to_be_read"),
]

# Tests that no mutant can turn red, with the reason. Keep this list short and honest.
NOT_KILLABLE: dict[str, str] = {
    # Declared here only when no plausible one-line fault breaks the test. Currently none:
    # a ROOM_CLI-ignoring mutant was dropped as EQUIVALENT, because the real room-cli wrapper
    # itself honours ROOM_CLI, so bypassing it in watchdog.py changes nothing observable here.
}

TEST_RE = re.compile(r"^(test_\w+) \(", re.M)
FAIL_RE = re.compile(r"^(?:FAIL|ERROR): (test_\w+) \(", re.M)


def run_tests(root: Path, test_file: str, verbose: bool = False) -> tuple[int, str]:
    cmd = [sys.executable, str(root / test_file)] + (["-v"] if verbose else [])
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=root)
    return p.returncode, p.stdout + p.stderr


def one(args):
    i, tmp, base, mutant = args
    name, rel, old, new, tf, guard = mutant
    work = Path(tmp) / f"m{i}"
    shutil.copytree(base, work)
    src = (work / rel).read_text()
    if src.count(old) != 1:
        return name, guard, None, f"pattern appears {src.count(old)}x in {rel}, need exactly 1 (mutant is stale)", set()
    (work / rel).write_text(src.replace(old, new))
    rc, out = run_tests(work, tf)
    failed = set(FAIL_RE.findall(out))
    shutil.rmtree(work, ignore_errors=True)
    return name, guard, rc != 0 and guard in failed, f"rc={rc}", failed


def main() -> int:
    bad: list[str] = []
    with tempfile.TemporaryDirectory(prefix="router-mut-") as tmp:
        base = Path(tmp) / "base"
        shutil.copytree(SKILL, base, ignore=shutil.ignore_patterns("__pycache__"))
        all_tests: dict[str, str] = {}
        for tf in SUITES:
            rc, out = run_tests(base, tf, verbose=True)
            if rc != 0:
                print(f"VOID: unmutated {tf} does not pass:\n{out[-1500:]}")
                return 2
            for t in TEST_RE.findall(out):
                all_tests[t] = tf
        killed: set[str] = set()
        with ThreadPoolExecutor(max_workers=4) as pool:
            for name, guard, red, detail, failed in pool.map(one, [(i, tmp, base, m) for i, m in enumerate(MUTANTS)]):
                if red is None:
                    bad.append(f"{name}: {detail}")
                    continue
                killed |= failed
                print(f"{'RED ' if red else 'LIVE'} {name}  [{guard}]")
                if not red:
                    bad.append(f"{name}: {guard} did not go red ({detail})")
        unknown = [t for t in killed if t not in all_tests]
        uncovered = sorted(t for t in all_tests if t not in killed and t not in NOT_KILLABLE)
        declared = sorted(t for t in NOT_KILLABLE if t in all_tests)
        stale_decl = sorted(t for t in NOT_KILLABLE if t not in all_tests or t in killed)
        print(f"\nmutants: {len(MUTANTS)}; tests: {len(all_tests)}; tests turned red by at least one mutant: "
              f"{len(killed & set(all_tests))}; declared not killable: {len(declared)}")
        for t in declared:
            print(f"  not killable: {t}: {NOT_KILLABLE[t]}")
        if uncovered:
            bad.append("tests no mutant turns red (add a mutant or declare it): " + ", ".join(uncovered))
        if stale_decl:
            bad.append("NOT_KILLABLE entries that are stale or now killed (remove them): " + ", ".join(stale_decl))
        if unknown:
            print(f"  note: failures seen for unlisted tests (subtests or helpers): {sorted(unknown)[:5]}")
    if bad:
        print("\nFAILED:\n  " + "\n  ".join(bad))
        return 1
    print("\nall mutants killed and every test accounted for")
    return 0


if __name__ == "__main__":
    sys.exit(main())
