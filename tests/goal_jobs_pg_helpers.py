"""tests/goal_jobs_pg_helpers.py — a throwaway Postgres database for the goal job SQL tests.

`database()` yields the URL of a NEW database holding exactly the three goal job
migrations, read from this checkout (so a planted defect in a copy of a migration is
what gets tested). The server is SCRATCH_DB_URL when set (CI's service container; it
must be localhost), otherwise a cluster started here from the local `postgres` binaries
and deleted afterwards. Never a remote database.

Supabase's default privileges are reproduced before the migrations run: anon,
authenticated and service_role get every new table and EXECUTE on every new function in
public. That is what makes "anon cannot execute" a real test of the migration's REVOKE.
"""
from __future__ import annotations

import contextlib
import glob
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

MIGRATIONS = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
FILES = ("20261108T000000_goal_analysis_jobs.sql", "20261108T010000_goal_analysis_job_functions.sql",
         "20261108T020000_goal_analysis_job_purge.sql")
APPLY_FAILED = "GOAL_JOBS_MIGRATION_APPLY_FAILED"  # mutants.py tells "not applied" from "caught" by this
_BOOTSTRAP = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN CREATE ROLE service_role NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;
"""


class MigrationApplyError(RuntimeError):
    pass


def bindir() -> str | None:
    """The directory of a local Postgres SERVER, so initdb and pg_ctl match its version."""
    found = shutil.which("postgres")
    candidates = [os.path.realpath(found)] if found else []
    candidates += sorted(glob.glob("/opt/homebrew/opt/postgresql@*/bin/postgres"), reverse=True)
    candidates += sorted(glob.glob("/usr/local/opt/postgresql@*/bin/postgres"), reverse=True)
    candidates += sorted(glob.glob("/usr/lib/postgresql/*/bin/postgres"), reverse=True)
    for path in candidates:
        d = os.path.dirname(path)
        if all(os.access(os.path.join(d, b), os.X_OK) for b in ("initdb", "pg_ctl")):
            return d
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _cluster(bins: str) -> Iterator[str]:
    data = tempfile.mkdtemp(prefix="goal-jobs-pg-")
    port = _free_port()
    ctl = os.path.join(bins, "pg_ctl")
    try:
        subprocess.run([os.path.join(bins, "initdb"), "-D", data, "-U", "postgres", "--auth=trust",
                        "-E", "UTF8", "--no-sync"], check=True, capture_output=True)
        opts = f"-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories='' -c fsync=off"
        subprocess.run([ctl, "-D", data, "-o", opts, "-l", os.path.join(data, "log"), "-w", "start"],
                       check=True, capture_output=True)
        try:
            yield f"postgresql://postgres@127.0.0.1:{port}/postgres"
        finally:
            subprocess.run([ctl, "-D", data, "-m", "immediate", "stop"], capture_output=True)
    finally:
        shutil.rmtree(data, ignore_errors=True)


def _apply(url: str) -> None:
    import psycopg

    with psycopg.connect(url, autocommit=True) as c:
        c.execute(_BOOTSTRAP)
        for name in FILES:
            try:
                c.execute((MIGRATIONS / name).read_text(encoding="utf-8"))
            except psycopg.Error as exc:
                raise MigrationApplyError(f"{APPLY_FAILED}: {name}: {exc}") from exc


@contextlib.contextmanager
def _fresh_database(server: str) -> Iterator[str]:
    import psycopg

    name = f"goal_jobs_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(server, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{name}"')
    parts = urlsplit(server)
    url = urlunsplit(parts._replace(path=f"/{name}"))
    try:
        _apply(url)
        yield url
    finally:
        with psycopg.connect(server, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@contextlib.contextmanager
def database(scratch: str, bins: str | None) -> Iterator[str]:
    if scratch:
        if urlsplit(scratch).hostname not in {"localhost", "127.0.0.1"}:
            raise RuntimeError("SCRATCH_DB_URL must point at a local throwaway database")
        with _fresh_database(scratch) as url:
            yield url
        return
    assert bins, "no SCRATCH_DB_URL and no local postgres binaries"
    with _cluster(bins) as server, _fresh_database(server) as url:
        yield url
