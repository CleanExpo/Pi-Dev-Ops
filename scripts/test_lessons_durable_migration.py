#!/usr/bin/env python3
"""Exercise RA-7119 migrations against a disposable local PostgreSQL cluster."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERAL = ROOT / "supabase" / "migration.sql"
LESSONS = ROOT / "supabase" / "migrations" / "20260804190000_lessons_durable.sql"
REQUIRED_BINARIES = ("postgres", "initdb", "pg_ctl", "psql", "createdb")


def postgres_bin(name: str) -> str:
    """Resolve one coherent server/client toolchain, not Homebrew's libpq shims."""
    pg_config = shutil.which("pg_config")
    if pg_config is None:
        raise RuntimeError("missing PostgreSQL binary: pg_config")
    bindir = Path(subprocess.check_output([pg_config, "--bindir"], text=True).strip())
    executable = bindir / name
    if not executable.is_file():
        raise RuntimeError(f"missing PostgreSQL binary: {executable}")
    return str(executable)


class Sandbox:
    def __init__(self, root: Path) -> None:
        self.data = root / "data"
        self.socket = root / "socket"
        self.log = root / "postgres.log"
        self.port = 54000 + os.getpid() % 1000
        self.socket.mkdir()
        self.running = False

    def env(self) -> dict[str, str]:
        return {
            **os.environ,
            "LC_ALL": "C",
            "PGHOST": str(self.socket),
            "PGPORT": str(self.port),
            "PGUSER": "postgres",
        }

    def run(self, args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            check=True,
            text=True,
            env=self.env(),
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
        )

    def start(self) -> None:
        self.run([postgres_bin("initdb"), "-D", str(self.data), "--username=postgres", "--auth=trust", "--no-locale", "--encoding=UTF8"])
        options = f"-F -p {self.port} -k {self.socket} -h ''"
        self.run([postgres_bin("pg_ctl"), "-D", str(self.data), "-l", str(self.log), "-o", options, "-w", "start"])
        self.running = True
        self.sql("postgres", "CREATE ROLE service_role NOLOGIN; CREATE ROLE anon NOLOGIN;")
        print(f"SANDBOX target=local-unix-socket:{self.socket} port={self.port} shared=false production=false")

    def stop(self) -> None:
        if self.running:
            self.run([postgres_bin("pg_ctl"), "-D", str(self.data), "-m", "fast", "-w", "stop"])
            self.running = False

    def create_database(self, name: str) -> None:
        self.run([postgres_bin("createdb"), name])

    def sql(self, database: str, statement: str) -> str:
        result = self.run(
            [postgres_bin("psql"), "-X", "-v", "ON_ERROR_STOP=1", "-At", "-d", database, "-c", statement],
            capture=True,
        )
        return (result.stdout or "").strip()

    def apply(self, database: str, path: Path, pass_number: int) -> None:
        result = self.run(
            [postgres_bin("psql"), "-X", "-v", "ON_ERROR_STOP=1", "-d", database, "-f", str(path)],
            capture=True,
        )
        output = result.stdout or ""
        marker = next((line.strip() for line in output.splitlines() if "migration complete" in line), "missing")
        if marker == "missing":
            raise AssertionError(f"completion marker missing for {path.name} pass {pass_number}")
        print(f"APPLY database={database} file={path.relative_to(ROOT)} pass={pass_number} exit=0 marker={marker!r}")


def expect(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"ASSERT {label}=PASS value={actual!r}")


def assert_contract(box: Sandbox, database: str, expected_rows: str) -> None:
    columns = box.sql(
        database,
        """SELECT string_agg(column_name || ':' || data_type || ':' || is_nullable, ',' ORDER BY ordinal_position)
           FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'lessons_durable';""",
    )
    expect(columns, "hash:text:NO,line:jsonb:NO,created_at:timestamp with time zone:NO", f"{database}.columns")
    expect(
        box.sql(
            database,
            """SELECT pg_get_constraintdef(oid)
               FROM pg_constraint
               WHERE conrelid = 'public.lessons_durable'::regclass AND contype = 'p';""",
        ),
        "PRIMARY KEY (hash)",
        f"{database}.primary_key",
    )
    expect(
        box.sql(
            database,
            """SELECT count(*)
               FROM pg_index i
               JOIN pg_attribute a
                 ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
               WHERE i.indexrelid = 'public.lessons_durable_created_at_idx'::regclass
                 AND i.indrelid = 'public.lessons_durable'::regclass
                 AND i.indnatts = 1 AND a.attname = 'created_at' AND NOT i.indisunique;""",
        ),
        "1",
        f"{database}.created_at_index",
    )
    expect(
        box.sql(database, "SELECT relrowsecurity FROM pg_class WHERE oid = 'public.lessons_durable'::regclass;"),
        "t",
        f"{database}.rls_enabled",
    )
    expect(
        box.sql(
            database,
            """SELECT count(*)
               FROM pg_policies
               WHERE schemaname = 'public' AND tablename = 'lessons_durable'
                 AND policyname = 'service_only' AND cmd = 'ALL'
                 AND roles = ARRAY['service_role']::name[] AND qual = 'true';""",
        ),
        "1",
        f"{database}.service_only_policy",
    )
    expect(box.sql(database, "SELECT count(*) FROM lessons_durable;"), expected_rows, f"{database}.row_count")


def assert_access_contract(box: Sandbox, database: str) -> None:
    box.sql(
        database,
        """GRANT USAGE ON SCHEMA public TO service_role, anon;
           GRANT SELECT, INSERT, UPDATE, DELETE ON lessons_durable TO service_role;
           GRANT SELECT ON lessons_durable TO anon;""",
    )
    service_output = box.sql(
        database,
        """SET ROLE service_role;
           WITH inserted AS (
             INSERT INTO lessons_durable (hash, line)
             VALUES ('access-probe', jsonb_build_object('lesson', 'service role allowed'))
             RETURNING hash
           ) SELECT hash FROM inserted;""",
    )
    expect(service_output.splitlines()[-1], "access-probe", f"{database}.service_role_write")
    anon_output = box.sql(database, "SET ROLE anon; SELECT count(*) FROM lessons_durable;")
    expect(anon_output.splitlines()[-1], "0", f"{database}.anon_default_deny")


def main() -> int:
    for name in REQUIRED_BINARIES:
        postgres_bin(name)
    if not GENERAL.is_file() or not LESSONS.is_file():
        raise RuntimeError("migration files are missing")

    with tempfile.TemporaryDirectory(prefix="ra7119-postgres-") as temp:
        box = Sandbox(Path(temp))
        try:
            box.start()

            box.create_database("fresh_install")
            box.apply("fresh_install", GENERAL, 1)
            box.apply("fresh_install", GENERAL, 2)
            expect(box.sql("fresh_install", "SELECT to_regclass('public.lessons_durable') IS NULL;"), "t", "general_schema.is_independent")
            box.apply("fresh_install", LESSONS, 1)
            box.apply("fresh_install", LESSONS, 2)
            assert_contract(box, "fresh_install", "0")

            box.create_database("lessons_only")
            box.apply("lessons_only", LESSONS, 1)
            box.apply("lessons_only", LESSONS, 2)
            assert_contract(box, "lessons_only", "0")
            assert_access_contract(box, "lessons_only")

            box.create_database("legacy_upgrade")
            box.sql(
                "legacy_upgrade",
                """CREATE TABLE lessons_durable (
                       hash TEXT PRIMARY KEY,
                       line JSONB NOT NULL,
                       created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                   );
                   CREATE INDEX lessons_durable_created_at_idx ON lessons_durable (created_at);
                   ALTER TABLE lessons_durable ENABLE ROW LEVEL SECURITY;
                   CREATE POLICY service_only ON lessons_durable FOR ALL TO service_role USING (true);
                   INSERT INTO lessons_durable (hash, line)
                   VALUES ('preserved-hash', jsonb_build_object('lesson', 'preserve me'));""",
            )
            box.apply("legacy_upgrade", LESSONS, 1)
            box.apply("legacy_upgrade", LESSONS, 2)
            assert_contract(box, "legacy_upgrade", "1")
            expect(
                box.sql("legacy_upgrade", "SELECT line->>'lesson' FROM lessons_durable WHERE hash = 'preserved-hash';"),
                "preserve me",
                "legacy_upgrade.data_preserved",
            )
        finally:
            box.stop()

    print("RESULT RA-7119 sandbox migration verification PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
