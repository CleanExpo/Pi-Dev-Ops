#!/usr/bin/env python3
"""Pi-Dev-Ops Model Farm — daemon-thread worker pool.
Watches for JSON task files in ~/.hermes/.farm/, dispatches to Claude/Codex CLI,
and writes results. No tmux, no detached processes. Spawn once per Hermes session."""
import json, os, pathlib, subprocess, sys, time, shutil, threading, uuid
import platform

# --- Config ---
FARM_DIR = pathlib.Path.home() / ".hermes" / ".farm"
FARM_DIR.mkdir(parents=True, exist_ok=True)
STOP_FILE = FARM_DIR / "farm.stop"

WORKERS = [
    {"name": "claude-1", "role": "judge",     "cli": "claude", "model": "opus",   "model_args": ["--model", "opus"]},
    {"name": "claude-2", "role": "auditor",   "cli": "claude", "model": "sonnet", "model_args": ["--model", "sonnet"]},
    {"name": "claude-3", "role": "strategist","cli": "claude", "model": "sonnet", "model_args": ["--model", "sonnet"]},
    {"name": "codex-1",  "role": "coder",     "cli": "codex",  "model": "o3",     "model_args": ["--model", "o3"]},
]

_threads = {}


def find_binary(name):
    """Find a CLI binary in PATH or common Windows locations."""
    path = shutil.which(name)
    if path:
        return path
    user = os.getenv("USERPROFILE", os.getenv("HOME", ""))
    for ext in (".exe", ".cmd", ""):
        for sub in ("WinGet\\Links", "WindowsApps", "Roaming\\npm", "Local\\npm"):
            cand = pathlib.Path(user) / "AppData" / sub / f"{name}{ext}"
            if cand.is_file():
                return str(cand)
    return None


def _write_health(name, status):
    f = FARM_DIR / f"{name}.health.json"
    data = {
        "worker": name,
        "status": status,
        "thread_ident": threading.current_thread().ident,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    f.write_text(json.dumps(data) + "\n", encoding="utf-8")


def worker_thread(cfg, cli_path, stop_event):
    """Runs in a background thread. Polls for tasks, dispatches to CLI."""
    name = cfg["name"]
    role = cfg["role"]
    log = FARM_DIR / f"{name}.log"
    try:
        _write_health(name, "starting")
        while not stop_event.is_set():
            # Process tasks
            for task in FARM_DIR.glob(f"{name}.in-*.json"):
                tid = task.stem.replace(f"{name}.in-", "")
                stim = time.time()
                try:
                    with open(task, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    prompt = data.get("prompt", "")
                    if not prompt:
                        result = {"status": "empty_prompt", "task_id": tid}
                    else:
                        out_path = FARM_DIR / f"{name}.out-{tid}.json"
                        with open(log, "a", encoding="utf-8") as lf:
                            lf.write(f"[{time.ctime()}] TASK {tid} prompt_len={len(prompt)}\n")
                        if role == "coder":
                            cmd = [cli_path, "exec", "--dangerously-auto-approve"] + cfg["model_args"] + [prompt]
                        else:
                            cmd = [cli_path, "--print", "--permission-mode", "bypassPermissions"] + cfg["model_args"] + [prompt]
                        try:
                            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                            with open(out_path, "w", encoding="utf-8") as fp:
                                fp.write(r.stdout)
                            if r.stderr:
                                with open(log, "a", encoding="utf-8") as lf:
                                    lf.write(f"  stderr: {r.stderr[:500]}\n")
                            status = "done" if r.returncode == 0 else "fail"
                            dur = time.time() - stim
                            with open(log, "a", encoding="utf-8") as lf:
                                lf.write(f"  status={status} rc={r.returncode} dur={dur:.1f}s len_out={len(r.stdout)}\n")
                        except subprocess.TimeoutExpired:
                            status = "timeout"
                            with open(out_path, "w", encoding="utf-8") as fp:
                                fp.write("TIMEOUT")
                        except Exception as exc:
                            status = "error"
                            with open(out_path, "w", encoding="utf-8") as fp:
                                fp.write(f"ERROR: {exc}")
                            with open(log, "a", encoding="utf-8") as lf:
                                lf.write(f"  ERROR: {exc}\n")
                        meta = FARM_DIR / f"{name}.out-{tid}.meta.json"
                        with open(meta, "w", encoding="utf-8") as fp:
                            json.dump({
                                "task_id": tid,
                                "status": status,
                                "worker": name,
                                "model": cfg["model"],
                                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            }, fp)
                except Exception as exc:
                    with open(log, "a", encoding="utf-8") as lf:
                        lf.write(f"  CRASH: {exc}\n")
                finally:
                    task.unlink(missing_ok=True)

            _write_health(name, "ready")
            time.sleep(2)
    except Exception as exc:
        with open(log, "a", encoding="utf-8") as lf:
            lf.write(f"FATAL: {exc}\n")
        _write_health(name, f"crashed: {exc}")


def _env_prep():
    """Augment PATH for Windows CLI locations."""
    user = os.getenv("USERPROFILE", os.getenv("HOME", ""))
    extra = []
    for sub in (
        "AppData/Local/Microsoft/WindowsApps",
        "AppData/Local/Microsoft/WinGet/Links",
        "AppData/Roaming/npm",
        "AppData/Local/npm",
    ):
        p = pathlib.Path(user) / sub
        if p.is_dir():
            extra.append(str(p))
    if extra:
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + os.pathsep.join(extra)


def start():
    _env_prep()

    binaries = {}
    for w in WORKERS:
        b = find_binary(w["cli"])
        if b is None:
            print(f"[FAIL] {w['name']}: binary not found for '{w['cli']}'")
        else:
            binaries[w["name"]] = b

    if not binaries:
        print("No CLI binaries found. Farm cannot start.")
        sys.exit(1)

    # Clear stop signal
    STOP_FILE.unlink(missing_ok=True)

    print(f"Binaries: {json.dumps({k: os.path.basename(v) for k, v in binaries.items()}, indent=2)}")

    for w in WORKERS:
        name = w["name"]
        if name not in binaries:
            continue
        # Kill any previous thread if name was reused
        if name in _threads:
            _threads[name]["stop_event"].set()
            time.sleep(0.2)
        evt = threading.Event()
        t = threading.Thread(
            target=worker_thread,
            args=(w, binaries[name], evt),
            name=f"farm-{name}",
            daemon=True,
        )
        t.start()
        _threads[name] = {"thread": t, "stop_event": evt, "started_at": time.time()}
        print(f"  [OK] {name} (thread {t.ident}) — {w['role']} ({w['cli']} {w['model']})")
        time.sleep(0.3)

    print(f"\n=== Farm started: {len(_threads)}/{len(WORKERS)} workers online ===")
    print(f"  python3 {__file__} --status")
    print(f"  python3 {__file__} --stop")
    return _threads


def status():
    total = len(WORKERS)
    alive = 0
    for w in WORKERS:
        name = w["name"]
        hb = FARM_DIR / f"{name}.health.json"
        state = "down"
        tid = None
        extra = ""
        if name in _threads:
            t = _threads[name]["thread"]
            tid = t.ident
            state = "running" if t.is_alive() else "dead"
            if t.is_alive():
                alive += 1
        if hb.exists():
            try:
                h = json.loads(hb.read_text())
                extra = f" health_last={h.get('status', '?')}"
            except: pass
        if tid:
            print(f"  [{state.upper():8}] {name} thread_id={tid}{extra}")
        else:
            print(f"  [{state.upper():8}] {name} (not started){extra}")
    print(f"\n{alive}/{total} running")
    return 0 if alive == total else 2 if alive >= 2 else 1


def stop():
    for name in list(_threads):
        _threads[name]["stop_event"].set()
        del _threads[name]
    print("Stop signals sent; daemon threads will exit at next sleep boundary.")
    STOP_FILE.write_text("stop", encoding="utf-8")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Pi-Dev-Ops Model Farm")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--start", action="store_true")
    args = ap.parse_args()

    if args.status:
        sys.exit(status())
    elif args.stop:
        sys.exit(stop())
    else:
        start()
        # Keep process alive so threads survive
        print("\nPress Ctrl+C to exit (or use --stop from another shell)")
        try:
            while True:
                time.sleep(5)
                if STOP_FILE.exists():
                    print("Stop file detected. Shutting down.")
                    break
        except KeyboardInterrupt:
            print("\nInterrupted. Use --stop to cleanly signal workers.")

