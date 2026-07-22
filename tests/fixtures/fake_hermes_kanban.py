"""Portable fake Hermes Kanban CLI used by isolation regression tests.

The adapter is pointed at ``sys.executable`` and invokes ``python kanban ...``.
Tests copy this module to a temporary working directory as ``kanban``; no shell,
chmod, or platform-specific wrapper is required.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def _arg_value(args: list[str], flag: str) -> str | None:
    try:
        return args[args.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=20)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks(
          id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT,
          tenant TEXT, idempotency_key TEXT, skills_json TEXT,
          created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS invocations(
          seq INTEGER PRIMARY KEY AUTOINCREMENT, argv_json TEXT NOT NULL,
          cwd TEXT NOT NULL, env_names_json TEXT NOT NULL,
          db_path TEXT, mode TEXT NOT NULL, created_at REAL NOT NULL
        );
        """
    )
    return connection


def main() -> int:
    args = sys.argv[1:]
    home = Path(os.environ["HOME"]).resolve()
    mode_file = home / "mode.txt"
    mode = mode_file.read_text(encoding="utf-8").strip() if mode_file.exists() else "normal"
    database = os.environ.get("HERMES_KANBAN_DB")

    audit = _connect(home / "audit.sqlite")
    audit.execute(
        "INSERT INTO invocations(argv_json,cwd,env_names_json,db_path,mode,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (json.dumps(args), os.getcwd(), json.dumps(sorted(os.environ)), database, mode, time.time()),
    )
    audit.commit()
    audit.close()

    if mode == "nonzero":
        return 19
    if args and args[0] == "kanban":
        args = args[1:]
    if not args or args[0] != "create":
        return 64

    title = args[-1]
    body = _arg_value(args, "--body")
    tenant = _arg_value(args, "--tenant")
    idempotency_key = _arg_value(args, "--idempotency-key")
    skills = [args[index + 1] for index, item in enumerate(args[:-1]) if item == "--skill"]
    task_id = "k-" + hashlib.sha256((idempotency_key or title).encode()).hexdigest()[:12]

    if mode == "noop":
        print(json.dumps({"task_id": task_id}))
        return 0

    target = Path(database).resolve() if database else home / "missing-db.sqlite"
    if mode == "wrong_db":
        target = home / "wrong.sqlite"
    omit = mode == "omit_one" and "[CFO@b3]" in title
    copies = 2 if mode == "duplicate" else 1
    if not omit:
        connection = _connect(target)
        for copy_number in range(copies):
            row_id = task_id if copy_number == 0 else f"{task_id}-dup"
            connection.execute(
                "INSERT OR REPLACE INTO tasks"
                "(id,title,body,tenant,idempotency_key,skills_json,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    row_id,
                    title,
                    body,
                    tenant,
                    idempotency_key,
                    json.dumps(skills),
                    time.time(),
                ),
            )
        connection.commit()
        snapshot = sqlite3.connect(str(home / "target_snapshot.sqlite"))
        connection.backup(snapshot)
        snapshot.close()
        connection.close()

    print(json.dumps({"task_id": task_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
