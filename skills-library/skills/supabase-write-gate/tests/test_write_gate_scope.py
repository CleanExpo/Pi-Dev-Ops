"""The database gate acts on database commands only, and the same way for Bash and PowerShell.

Grill 18 (07/11/2026). One resume run hit three refusals of safe, read-only commands
from this gate, none of which touched a database:
  * `wsl.exe -e bash -lc '... gh api rate_limit ...'` - "given a command built by substitution"
  * `wsl.exe -e bash /mnt/c/.../gh-probe.sh`         - "fed a command this gate cannot read"
and the same command then ran unchecked through the PowerShell tool, because the gate was
registered on the Bash matcher only. So the gate both over-blocked and had a gap.

The decision: a shell command is checked only when it names a database surface (the
supabase CLI, a PostgreSQL client, a migration tool, a *.supabase.* host, a postgres URL,
a database driver), directly or inside a script file it names. Everything else is left to
Claude Code's own permission system and the auto-mode classifier. Bash and PowerShell
follow the one rule. The Supabase MCP allow-list is unchanged.

Every block case below must fail on the code before the change only where the change
fixes something (PowerShell, script bodies), and every pass case reproduces a real refusal.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GATE = REPO / "hooks" / "PreToolUse" / "supabase_write_gate.py"
INSTALLER = REPO / "skills" / "supabase-write-gate" / "scripts" / "install_supabase_write_gate.py"
SHELL_TOOLS = ("Bash", "PowerShell")

# The 07/11 command, byte for byte (orchestrator session 679dbfcf).
WSL_RATE_LIMIT_LOOP = (
    "wsl.exe -e bash -lc 'cd ~; for i in 1 2 3 4 5 6 7 8 9 10; do s=$(date +%s.%N); "
    "if timeout 30 env -i HOME=$HOME PATH=/usr/local/bin:/usr/bin:/bin gh api rate_limit "
    "-q .resources.core.remaining >/tmp/rl.$i 2>&1; then r=OK; else "
    "r=\"FAIL($(head -c 120 /tmp/rl.$i))\"; fi; e=$(date +%s.%N); "
    "printf \"%d %s %.1fs\\n\" $i \"$r\" $(echo \"$e - $s\" | bc); done' 2>&1 "
    "| tr -d '\\0' | grep -v bogus"
)

# The 07/11 probe script, byte for byte.
GH_PROBE = """#!/bin/bash
# Read-only probe: 10 gh api rate_limit calls from WSL with a clean PATH.
cd "$HOME" || exit 1
ok=0
for i in 1 2 3 4 5 6 7 8 9 10; do
  s=$(date +%s%N)
  if timeout 30 env -i HOME="$HOME" PATH=/usr/local/bin:/usr/bin:/bin gh api rate_limit -q .resources.core.remaining >"/tmp/rl.$i" 2>&1; then
    r=OK; ok=$((ok+1))
  else
    r="FAIL: $(head -c 120 "/tmp/rl.$i" | tr '\\n' ' ')"
  fi
  e=$(date +%s%N)
  echo "$i $r $(( (e - s) / 1000000 )) ms"
done
echo "TOTAL_OK=$ok/10"
"""

REMOTE = "db.abcdefghijklmnop.supabase.co"


def wsl_path(path: Path) -> str:
    """How WSL names a Windows file: C:\\x\\y -> /mnt/c/x/y. POSIX paths stay as they are."""
    text = str(path).replace("\\", "/")
    if len(text) > 1 and text[1] == ":":
        return f"/mnt/{text[0].lower()}{text[2:]}"
    return text


_PARITY = None  # set only by EarlyPassNeverNarrowerOnTheTestCorpus while it runs the suite


class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(self.dir), USERPROFILE=str(self.dir))

    def tearDown(self):
        self.tmp.cleanup()

    def run_gate(self, tool: str, tool_input: dict, cwd=None) -> subprocess.CompletedProcess:
        if _PARITY is not None and tool in ("Bash", "PowerShell") \
                and not isinstance(self, NonDatabaseCommandsPass):
            _PARITY.check(tool, str(tool_input.get("command", "")), cwd)
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
        return subprocess.run([sys.executable, str(GATE)], input=json.dumps(payload),
                              capture_output=True, text=True, env=self.env, timeout=60,
                              cwd=cwd)

    def shell(self, tool: str, command: str, cwd=None) -> subprocess.CompletedProcess:
        return self.run_gate(tool, {"command": command}, cwd)

    def script(self, name: str, body: str) -> Path:
        path = self.dir / name
        path.write_text(body, encoding="utf-8")
        return path


class DatabaseWritesStayBlocked(GateCase):
    """A database write is refused through BOTH shell tools."""

    def block_cases(self):
        deploy_sh = self.script("deploy.sh", "#!/bin/bash\nset -e\nnpx supabase db push\n")
        deploy_ps1 = self.script("deploy.ps1", "supabase db push --linked\n")
        drop_sql = f'psql -h {REMOTE} -c "DROP TABLE users"'
        return [
            f'psql "postgresql://postgres@{REMOTE}:5432/postgres" -c "DELETE FROM users"',
            drop_sql,
            "supabase db push",
            "npx supabase db reset --linked",
            "npx prisma migrate deploy",
            f"curl -X POST https://abcdefghijklmnop.supabase.co/rest/v1/users -d '{{}}'",
            "curl -X DELETE https://api.supabase.com/v1/projects/abcdefghijklmnop",
            'psql "$DATABASE_URL" -c "UPDATE users SET admin = true"',
            f"bash {deploy_sh.as_posix()}",
            f"wsl.exe -e bash {wsl_path(deploy_sh)}",
            f"powershell -NoProfile -File {deploy_ps1.as_posix()}",
            f"pwsh -File \"{deploy_ps1}\"",
            f"bash -c '{drop_sql}'",
        ]

    def test_powershell_unquoted_windows_path(self):
        # PowerShell keeps backslashes; Bash itself would eat them, so this is PowerShell only.
        ps1 = self.script("deploy.ps1", "supabase db push --linked\n")
        for command in (f"powershell -NoProfile -File {ps1}", f"& {ps1}"):
            with self.subTest(command=command):
                self.assertEqual(self.shell("PowerShell", command).returncode, 2, command)

    def test_writes_blocked_in_bash_and_powershell(self):
        for tool in SHELL_TOOLS:
            for command in self.block_cases():
                with self.subTest(tool=tool, command=command):
                    result = self.shell(tool, command)
                    self.assertEqual(result.returncode, 2, f"ALLOWED via {tool}: {command}")
                    self.assertIn("Supabase write gate BLOCKED", result.stderr)


class ReviewBypassesStayClosed(GateCase):
    """Independent review of 34a601ae: the early pass read text, not the command run.

    Each case passed the gate at 34a601ae (exit 0) while the full check would refuse it.
    The host 10.1.2.3 is a placeholder remote address, never a real one.
    """

    def test_quote_split_client_names_in_bash(self):
        for command in ('p"sql" -h 10.1.2.3 -c "DROP TABLE users"',
                        "ps\\ql -h 10.1.2.3 -c \"DROP TABLE users\"",
                        'npx s"upabase" db push --linked',
                        'npx p"risma" migrate deploy'):
            with self.subTest(command=command):
                self.assertEqual(self.shell("Bash", command).returncode, 2, command)

    def test_powershell_backtick_and_invoke_expression(self):
        for command in ('ps`ql -h 10.1.2.3 -c "DROP TABLE users"',
                        f'ps`ql -h {REMOTE} -c "DROP TABLE users"',
                        f"Invoke-Expression 'psql -h {REMOTE} -c \"DROP TABLE users\"'",
                        f"iex 'psql -h {REMOTE} -c \"DROP TABLE users\"'"):
            with self.subTest(command=command):
                self.assertEqual(self.shell("PowerShell", command).returncode, 2, command)

    def test_scripts_the_early_pass_could_not_read(self):
        drop = 'psql -h 10.1.2.3 -c "DROP TABLE users"\n'
        bare = self.script("deploy", drop)                                  # no suffix, no #!
        code = self.script("migrate", "import psycopg2\nc = psycopg2.connect(host='10.1.2.3')\n"
                                      "c.cursor().execute('DELETE FROM users')\n")
        big = self.script("big.sh", "#!/bin/bash\n" + "# padding\n" * 110_000 + drop)
        sub = self.dir / "sub"
        sub.mkdir()
        (sub / "write.sh").write_text("#!/bin/bash\n" + drop, encoding="utf-8")
        for command in (f"bash {bare.as_posix()}",
                        f"python {code.as_posix()}",
                        f"bash {big.as_posix()}",
                        f"cd {sub.as_posix()} && bash write.sh"):
            with self.subTest(command=command):
                self.assertEqual(self.shell("Bash", command).returncode, 2, command)

    def test_encoded_payloads_the_full_check_already_reads(self):
        """The early pass must use the same decoders bash_reason already has.

        A PowerShell -EncodedCommand / -enc UTF-16LE body, and a python/node -c
        program that decodes then executes, name no client in the outer command.
        Skipping the full check here lets a remote write through (security review
        of bb6ec299). Harmless encoded payloads still pass.
        """
        drop = f'psql -h {REMOTE} -c "DROP TABLE users"'
        encoded = base64.b64encode(drop.encode("utf-16-le")).decode("ascii")
        py_drop = (
            "import base64,os; os.system(base64.b64decode("
            + repr(base64.b64encode(drop.encode()).decode("ascii"))
            + ").decode())"
        )
        for tool, command in (
            ("PowerShell", f"powershell -NoProfile -EncodedCommand {encoded}"),
            ("PowerShell", f"-EncodedCommand {encoded}"),
            ("Bash", f"powershell -NoProfile -EncodedCommand {encoded}"),
            ("Bash", f"pwsh -enc {encoded}"),
            ("Bash", f"python -c {json.dumps(py_drop)}"),
            ("PowerShell", f"python -c {json.dumps(py_drop)}"),
        ):
            with self.subTest(tool=tool, command=command[:80]):
                result = self.shell(tool, command)
                self.assertEqual(result.returncode, 2, f"ALLOWED via {tool}: {command}\n{result.stderr}")

        hello = base64.b64encode("Get-Date".encode("utf-16-le")).decode("ascii")
        for tool, command in (
            ("PowerShell", f"-EncodedCommand {hello}"),
            ("Bash", f"python -c {json.dumps('print(1)')}"),
        ):
            with self.subTest(pass_cmd=command[:80]):
                result = self.shell(tool, command)
                self.assertEqual(result.returncode, 0, f"{command}\n{result.stderr}")

    def test_shell_decoders_feeding_a_runner(self):
        """Decode-then-execute is one kind, whatever does the decoding (adoption review of 59ad0e9).

        59ad0e9 taught the early pass the python/node decoders only. A shell decoder piped into
        a shell, eval, a process substitution or PowerShell's iex hid the same remote write: main
        refused every Bash case here (the full check refuses a stdin-fed shell and eval), the PR
        head let them all through. A decode with nothing that runs the result still passes.
        """
        drop = f'psql -h {REMOTE} -c "DROP TABLE users"'
        b64 = base64.b64encode(drop.encode()).decode("ascii")
        ps_text = f"[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64}'))"
        for tool, command in (
            ("Bash", f"echo {b64} | base64 -d | bash"),
            ("Bash", f"echo {b64} | base64 --decode | sh"),
            ("Bash", f"echo {b64} | base64 -di | bash"),
            ("Bash", f"echo {b64} | base64 -id | bash"),
            ("Bash", f"echo {b64} | base64.exe -d | bash"),
            ("Bash", f"echo {b64} | xxd.exe -r -p | bash"),
            ("PowerShell", f"echo {b64} | base64.exe -d | bash"),
            ("Bash", f"echo {b64} | env -i base64 -d | bash"),
            ("Bash", f"echo {b64} | sudo -u root base64 -d | bash"),
            ("PowerShell", f"echo {b64} | env -i base64 -d | bash"),
            ("PowerShell", f"echo {b64} | sudo -u root base64 -d | bash"),
            ("Bash", f'eval "$(echo {b64} | base64 -d)"'),
            ("Bash", f"bash <(echo {b64} | base64 -D)"),
            ("Bash", f"printf %s {b64} | openssl base64 -d -A | zsh"),
            ("PowerShell", f"{ps_text} | iex"),
            ("PowerShell", f"{ps_text} | Invoke-Expression"),
        ):
            with self.subTest(tool=tool, command=command[:80]):
                result = self.shell(tool, command)
                self.assertEqual(result.returncode, 2, f"ALLOWED via {tool}: {command}\n{result.stderr}")

        for tool, command in (
            ("Bash", "echo aGVsbG8= | base64 -d"),
            ("Bash", "echo aGVsbG8= | base64 -d > out.txt && cat deploy.sh"),
            ("PowerShell", "[Convert]::FromBase64String('aGVsbG8=')"),
        ):
            with self.subTest(pass_cmd=command):
                result = self.shell(tool, command)
                self.assertEqual(result.returncode, 0, f"{command}\n{result.stderr}")

    def test_unreadability_is_not_a_pass(self):
        """Security review of 59ad0e9: three fail-open paths, one kind.

        If this gate cannot see the script that will run, it must not permit.
        The early pass already treated an oversize file as a surface, then
        bash_reason read None and continued. cd bases were collected for the
        early pass and dropped for the full check. Depth 3 returned False.
        """
        drop = 'psql -h 10.1.2.3 -c "DROP TABLE users"\n'
        py_drop = ("import psycopg2\nc = psycopg2.connect(host='10.1.2.3')\n"
                   "c.cursor().execute('DELETE FROM users')\n")
        padding = "# padding\n" * 110_000
        # Distinct names from the cwd decoys below: the decoys must not overwrite
        # the oversize files the first three cases invoke by absolute path.
        big_py = self.script("big_migrate.py", "#!/usr/bin/env python3\n" + padding + py_drop)
        big_ps1 = self.script("deploy.ps1", padding + "supabase db push --linked\n")
        big_direct = self.script("deploy.sh", "#!/bin/bash\n" + padding + drop)
        sub = self.dir / "sub"
        sub.mkdir()
        (sub / "migrate.py").write_text(py_drop, encoding="utf-8")
        (sub / "write.sh").write_text("#!/bin/bash\n" + drop, encoding="utf-8")
        (self.dir / "migrate.py").write_text("print('cwd decoy')\n", encoding="utf-8")
        (self.dir / "write.sh").write_text("#!/bin/bash\necho hello\n", encoding="utf-8")
        d = self.script("d.sh", "#!/bin/bash\n" + drop)
        c = self.script("c.sh", f"#!/bin/bash\nbash {d.as_posix()}\n")
        b = self.script("b.sh", f"#!/bin/bash\nbash {c.as_posix()}\n")
        a = self.script("a.sh", f"#!/bin/bash\nbash {b.as_posix()}\n")
        cases = [
            ("Bash", f"python {big_py.as_posix()}"),
            ("Bash", f"pwsh -File {big_ps1.as_posix()}"),
            ("Bash", big_direct.as_posix()),
            ("Bash", f"cd {sub.as_posix()} && python migrate.py"),
            ("Bash", f"cd {sub.as_posix()} && ./write.sh"),
            ("PowerShell", f"Set-Location {sub.as_posix()}; python migrate.py"),
            ("Bash", f"bash {a.as_posix()}"),
        ]
        for tool, command in cases:
            with self.subTest(tool=tool, command=command):
                result = self.shell(tool, command)
                self.assertEqual(result.returncode, 2, f"ALLOWED via {tool}: {command}\n{result.stderr}")

    def test_every_encoded_command_spelling(self):
        """PowerShell takes any unique prefix of -EncodedCommand, and -e / -ec as aliases.

        Cursor review of b92001c2: `powershell -e <b64>` and `-en` were refused on main
        (an unreadable shell input) but passed here, because the early pass decoded only
        -EncodedCommand / -enc. -ec, -encoded and -encodedc reached neither decoder. One
        owner (_is_ps_encoded_flag) now names the flag for both passes.
        """
        drop = f'psql -h {REMOTE} -c "DROP TABLE users"'
        encoded = base64.b64encode(drop.encode("utf-16-le")).decode("ascii")
        hello = base64.b64encode("Get-Date".encode("utf-16-le")).decode("ascii")
        flags = ("-EncodedCommand", "-encodedcommand", "-enc", "-e", "-E", "-en", "-ec",
                 "-encoded", "-encodedc", "-EncodedC")
        for flag in flags:
            for tool, command in (("Bash", f"powershell -NoProfile {flag} {encoded}"),
                                  ("Bash", f"pwsh {flag} {encoded}"),
                                  ("PowerShell", f"powershell {flag} {encoded}"),
                                  ("PowerShell", f"{flag} {encoded}")):
                with self.subTest(tool=tool, command=command[:60]):
                    result = self.shell(tool, command)
                    self.assertEqual(result.returncode, 2, f"ALLOWED via {tool}: {command}")
            for tool, command in (("Bash", f"pwsh {flag} {hello}"),
                                  ("PowerShell", f"{flag} {hello}")):
                with self.subTest(pass_cmd=command[:60], tool=tool):
                    result = self.shell(tool, command)
                    self.assertEqual(result.returncode, 0, f"{command}\n{result.stderr}")
        # PowerShell reached through another program still decodes.
        for tool, command in (("Bash", f"cmd /c powershell -NoProfile -e {encoded}"),
                              ("Bash", f"sudo pwsh -en {encoded}"),
                              ("PowerShell", f"cmd /c powershell -encoded {encoded}")):
            with self.subTest(tool=tool, command=command[:60]):
                result = self.shell(tool, command)
                self.assertEqual(result.returncode, 2, f"ALLOWED via {tool}: {command}")
        # psql's own -e (echo queries) is not an encoded command and shields nothing.
        result = self.shell("Bash", f'psql -e -h {REMOTE} -c "DROP TABLE users"')
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_a_later_cd_does_not_hide_an_earlier_script(self):
        """Codex review of 2808e67b: `bash write.sh && cd sub` passed; main refuses it.

        The early pass resolved write.sh against the LATER cd and read the harmless decoy
        in sub/. A script runs in the folder current when its segment runs.
        """
        self.script("write.sh", f'psql -h {REMOTE} -c "DROP TABLE users"\n')
        (self.dir / "sub").mkdir()
        (self.dir / "sub" / "write.sh").write_text("echo safe\n", encoding="utf-8")
        for tool, command in (("Bash", "bash write.sh && cd sub"),
                              ("Bash", "bash ./write.sh; cd sub; ls"),
                              ("PowerShell", "bash write.sh; Set-Location sub")):
            with self.subTest(tool=tool, command=command):
                result = self.shell(tool, command, cwd=str(self.dir))
                self.assertEqual(result.returncode, 2, f"ALLOWED via {tool}: {command}")
        # The decoy is what runs after the cd: harmless, so it passes.
        result = self.shell("Bash", "cd sub && bash write.sh", cwd=str(self.dir))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_another_programs_e_flag_is_data(self):
        """Codex review of 7251fea9: `grep -e <base64 of a DROP> notes.txt` was refused.

        grep reads -e as a pattern; only PowerShell decodes base64 into a command. Main
        67813918 allows every one of these, in Bash and in the PowerShell tool.
        """
        drop = f'psql -h {REMOTE} -c "DROP TABLE users"'
        encoded = base64.b64encode(drop.encode("utf-16-le")).decode("ascii")
        for command in (f"grep -e {encoded} notes.txt", f"grep -ec {encoded} notes.txt",
                        f"sed -e {encoded} notes.txt", f"echo -e {encoded}",
                        f"git log -e {encoded}",
                        # Codex review of 678ca8bc: a `powershell` WORD is not PowerShell
                        # running. The program comes from _segment_command, not a word match.
                        # (`echo powershell -en <b64>` is left out: main refuses it too,
                        # because echo is not a DATA_CONSUMER and the rescan finds powershell.)
                        f"grep powershell -e {encoded} notes.txt",
                        f"grep -e pwsh -e {encoded} notes.txt"):
            for tool in ("Bash", "PowerShell"):
                with self.subTest(tool=tool, command=command[:40]):
                    result = self.shell(tool, command)
                    self.assertEqual(result.returncode, 0, f"REFUSED via {tool}: {command}\n{result.stderr}")

    def test_issue_185_encoded_spellings(self):
        """Security review threads on #185: every way PowerShell reads a switch is one owner.

        A colon value, a slash or doubled or typographic dash, and a payload .NET accepts but
        a strict decoder does not, all passed the early pass while the same write with a
        space-separated -EncodedCommand blocks. A flag whose value cannot be read is refused.
        """
        drop = f'psql -h {REMOTE} -c "DROP TABLE users"'
        encoded = base64.b64encode(drop.encode("utf-16-le")).decode("ascii")
        hello = base64.b64encode("Get-Date".encode("utf-16-le")).decode("ascii")
        tabbed = base64.b64encode(drop.replace(" ", "\t").encode("utf-16-le")).decode("ascii")
        for flag in ("-EncodedCommand", "-e", "-enc", "-ec", "-ENCODEDCOMMAND",
                     "/EncodedCommand", "/e", "/enc", "/ec", "/ENC",
                     "--EncodedCommand", "–EncodedCommand"):
            for command in (f"powershell {flag} {encoded}", f"pwsh {flag}:{encoded}",
                            f"sudo pwsh -NoProfile {flag}:{encoded}",
                            f"cmd /c powershell {flag}:{encoded}"):
                for tool in SHELL_TOOLS:
                    with self.subTest(tool=tool, command=command[:60]):
                        result = self.shell(tool, command)
                        self.assertEqual(result.returncode, 2, f"ALLOWED via {tool}: {command}")
            for command in (f"pwsh {flag} {hello}", f"pwsh {flag}:{hello}"):
                for tool in SHELL_TOOLS:
                    with self.subTest(pass_cmd=command[:60], tool=tool):
                        result = self.shell(tool, command)
                        self.assertEqual(result.returncode, 0, f"{command}\n{result.stderr}")
        for flag in ("-EncodedCommand:", "-e:"):
            result = self.shell("PowerShell", f"{flag}{encoded}")
            self.assertEqual(result.returncode, 2, f"ALLOWED: {flag}<b64> as the tool's own arguments")
        spaced = encoded[:12] + " " + encoded[12:]
        for command in (f'pwsh -e "{spaced}"', f"pwsh -e {tabbed}", "pwsh -e not_base64!!"):
            with self.subTest(command=command[:60]):
                self.assertEqual(self.shell("Bash", command).returncode, 2, f"ALLOWED: {command}")
        # Only PowerShell reads these; a colon on another program's -e is still data.
        for command in (f"grep -e:{encoded} notes.txt", "pwsh -Command Get-Date"):
            with self.subTest(pass_cmd=command[:60]):
                result = self.shell("Bash", command)
                self.assertEqual(result.returncode, 0, f"{command}\n{result.stderr}")
        # A slash path is not a slash switch.
        self.assertFalse(_load_gate()._is_ps_encoded_flag("/etc/foo.ps1"))

    def test_issue_185_inline_runners(self):
        """Security review threads on #185: an inline bun or deno program skipped the full check.

        One predicate (_inline_program_writes) now answers for both passes, on the programs
        one reader (_inline_programs) finds. Programs that write nothing still pass.
        """
        program = "await sql`DROP TABLE users`"
        for command in (f"bun -e '{program}'", f"bun --eval '{program}'",
                        f"bun --eval='{program}'", f"bun -p '{program}'",
                        f"bun --print '{program}'", f"bun --silent -e '{program}'",
                        f"deno eval '{program}'", f"deno -e '{program}'",
                        f"deno --eval '{program}'", f"deno eval --ts '{program}'",
                        f"deno eval --ext=ts '{program}'", f"env bun -e '{program}'",
                        f"timeout 5 bun -e '{program}'",
                        # Double quotes: PowerShell and bash both act on a backtick there,
                        # so the nested program is written without one.
                        "bash -c \"bun -e 'await run(DROP TABLE users)'\"",
                        "pwsh -com \"bun -e 'await run(DROP TABLE users)'\"",
                        "pwsh -Command:\"bun -e 'await run(DROP TABLE users)'\"",
                        "pwsh /Command \"bun -e 'await run(DROP TABLE users)'\""):
            for tool in SHELL_TOOLS:
                with self.subTest(tool=tool, command=command):
                    result = self.shell(tool, command)
                    self.assertEqual(result.returncode, 2, f"ALLOWED via {tool}: {command}")
        for command in ("bun -e 'console.log(1)'", "deno eval 'console.log(1)'",
                        "bun x vitest run", "bun run build", "deno run main.ts"):
            for tool in SHELL_TOOLS:
                with self.subTest(pass_cmd=command, tool=tool):
                    result = self.shell(tool, command)
                    self.assertEqual(result.returncode, 0, f"{command}\n{result.stderr}")
        # A tool stepped over by bun is still classified as itself.
        self.assertEqual(self.shell("Bash", "bun x supabase db push --linked").returncode, 2)

    def test_harmless_files_and_glue_still_pass(self):
        tool = self.script("tool", "echo hello\n")                         # no suffix, no #!
        notes = self.script("notes", "nothing to see\n")
        for tool_name, command in (("Bash", f"bash {tool.as_posix()}"),
                                   ("Bash", f"cat {notes.as_posix()}"),
                                   ("Bash", 'e"cho" hello'),
                                   ("PowerShell", "Write-Output `\"hi`\"")):
            with self.subTest(tool=tool_name, command=command):
                result = self.shell(tool_name, command)
                self.assertEqual(result.returncode, 0, f"{command}\n{result.stderr}")


def _load_gate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("supabase_write_gate_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ParityProbe:
    """Runs both passes in-process on one command, at the moment a test sends it.

    Called from GateCase.run_gate, so fixture files still exist and the working folder
    is the test's own. A violation is a command the full check refuses while the early
    pass lets it skip the full check.
    """

    def __init__(self, gate):
        self.gate = gate
        self.checked = self.refused = 0
        self.violations: list[str] = []

    def check(self, tool: str, command: str, cwd=None) -> None:
        old = os.getcwd()
        try:
            if cwd:
                os.chdir(cwd)
            seen = self.gate._powershell_as_posix(command) if tool == "PowerShell" else command
            self.checked += 1
            reason = self.gate.bash_reason(seen)
            if reason is None:
                return
            self.refused += 1
            if not (self.gate.names_database_surface(command)
                    or self.gate.names_database_surface(seen)):
                self.violations.append(f"{tool}: {command[:150]!r} (full check: {reason[:90]})")
        except Exception as exc:  # noqa: BLE001 -- a crash in either pass is a finding too
            self.violations.append(f"{tool}: {command[:150]!r} raised {exc!r}")
        finally:
            os.chdir(old)


def _main_test_commands() -> list[tuple[str, str]]:
    """Shell commands in main's own gate test (scripts/test_supabase_gate.sh)."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "test_supabase_gate.sh"
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        start = line.find("'{")
        if not line.lstrip().startswith("check ") or start < 0:
            continue
        try:
            payload = json.loads(line[start + 1:line.rindex("}'") + 1])
        except ValueError:
            continue
        if payload.get("tool_name") in ("Bash", "PowerShell"):
            found.append((payload["tool_name"], payload["tool_input"]["command"]))
    return found


class EarlyPassNeverNarrowerOnTheTestCorpus(unittest.TestCase):
    """K6 as a property: no command any gate test sends may pass the early pass while the
    full check refuses it. The corpus is every shell command this file's GateCase tests
    send (Bash and PowerShell) plus main's own gate test, so a new test case is checked
    here without editing this class. NonDatabaseCommandsPass is left out by name: those
    are the founder's locked scope cases (07/11 refusals), which pass because they name no
    database surface even though the full check reads them as undecidable.
    """

    def test_every_test_command(self):
        global _PARITY
        probe = _ParityProbe(_load_gate())
        classes, todo = [], list(GateCase.__subclasses__())
        while todo:
            cls = todo.pop()
            classes.append(cls)
            todo.extend(cls.__subclasses__())
        suite = unittest.TestSuite(unittest.TestLoader().loadTestsFromTestCase(cls)
                                   for cls in classes)
        _PARITY = probe
        try:
            suite.run(unittest.TestResult())
            main_commands = _main_test_commands()
            for tool, command in main_commands:
                probe.check(tool, command)
        finally:
            _PARITY = None
        self.assertGreaterEqual(len(main_commands), 1, "main's gate test was not read")
        self.assertGreater(probe.checked, 80, "the corpus no longer reaches the probe")
        self.assertGreater(probe.refused, 40, "the corpus no longer exercises the full check")
        self.assertEqual(probe.violations, [], "early pass narrower than the full check:\n"
                         + "\n".join(probe.violations[:25]))


class EarlyPassReadsWhatTheFullCheckReads(unittest.TestCase):
    """K6 parity: the early pass may never let a payload skip a full check that refuses it.

    Three K6 hits (encoded payloads, cd bases and unreadable scripts, -e / -en) were each a
    payload one pass read and the other did not. Programs come from the full check's own
    table (full_check_unwraps) and flags from the decoders' own tables, so a program or a
    spelling added to the full check is tested here without editing this file.
    OPAQUE_EXECUTORS (eval, source, at) are left out on purpose: they refuse without reading
    anything, which is the named limit "a database reached with no surface named".
    """

    def test_no_payload_the_full_check_refuses_skips_it(self):
        import shlex
        gate = _load_gate()
        drop = f'psql -h {REMOTE} -c "DROP TABLE users"'
        payloads = {
            "plain": drop,
            "utf16-b64": base64.b64encode(drop.encode("utf-16-le")).decode("ascii"),
            "inline-write": "await sql`DROP TABLE users`",
        }
        # -EncodedCommand belongs to PowerShell only (gate.POWERSHELLS); every other
        # program gets the generic payload flags. The bare spelling is the PowerShell
        # tool, which is itself the interpreter.
        ps_spellings = ["-EncodedCommand", "-enc", "-e", "-en", "-ec", "-encoded", "-encodedc",
                        "/EncodedCommand", "/e", "/ec", "--EncodedCommand", "–e"]
        generic = sorted(gate._COMMAND_FLAGS) + ["--command=X"]
        programs = sorted(gate.full_check_unwraps() - gate.OPAQUE_EXECUTORS)
        self.assertGreaterEqual(len(programs), 15, programs)
        self.assertTrue(gate.POWERSHELLS <= set(programs), gate.POWERSHELLS)
        shapes = [(program, flag) for program in programs for flag in generic]
        shapes += [(program, flag) for program in sorted(gate.POWERSHELLS) for flag in ps_spellings]
        shapes += [("", flag) for flag in ps_spellings]
        shapes += [("cmd /c powershell -NoProfile", flag) for flag in ps_spellings]
        shapes += [(runner, flag) for runner, flags in sorted(gate.INLINE_RUNNERS.items())
                   for flag in flags]
        refused = narrower = 0
        failures = []
        for program, flag in shapes:
                for kind, payload in payloads.items():
                    # An inline program is only one for a runner; a shell reads its backticks
                    # as substitution, which is the separate 07/11 scope decision.
                    if kind == "inline-write" and program not in gate.INLINE_RUNNERS:
                        continue
                    if flag == "--command=X":
                        command = f"{program} {shlex.quote('--command=' + payload)}"
                    else:
                        command = f"{program} {flag} {shlex.quote(payload)}".lstrip()
                    if program == "ssh":
                        command = f"ssh -o BatchMode=yes box {shlex.quote(payload)}"
                    for seen in (command, gate._powershell_as_posix(command)):
                        if gate.bash_reason(seen) is None:
                            continue
                        refused += 1
                        if not (gate.names_database_surface(command)
                                or gate.names_database_surface(seen)):
                            narrower += 1
                            failures.append(f"{kind}: {seen}")
        self.assertGreater(refused, 100, "the corpus no longer exercises the full check")
        self.assertEqual(narrower, 0, "early pass narrower than the full check:\n"
                         + "\n".join(failures[:20]))

    def test_a_decoder_feeding_a_shell_never_skips_the_full_check(self):
        """K6 again, post-merge Codex review of cdd35fa3: `base64 -di | bash` skipped the full check.

        The early pass recognised a shell decoder by its option spelling (`-d` or `--decode` as
        a separate word), so the combined `-di`, `-id`, and xxd's own flags were missed while
        the full check refuses every stdin-fed shell. The decoder is now known by its program
        name alone (gate.SHELL_DECODERS); no option is read. Cases come from that one list.
        """
        import shlex
        gate = _load_gate()
        decoders = sorted(getattr(gate, "SHELL_DECODERS",
                                  {"base64", "base32", "basenc", "openssl", "xxd"}))
        b64 = base64.b64encode(f'psql -h {REMOTE} -c "DROP TABLE users"'.encode()).decode()
        spellings = ["-d", "-di", "-id", "-D", "--decode", "--ignore-garbage --decode",
                     "-r -p", "base64 -d -A", ""]
        # Review of 4715bdaa: `base64.exe` and `xxd.exe` (Git for Windows) slipped past a text
        # search. The program name comes from _walk, so every spelling of the program counts.
        programs = [p for d in decoders
                    for p in (d, f"{d}.exe", f"{d.upper()}.EXE", f"/usr/bin/{d}")]
        failures = []
        for decoder in programs:
            for spelling in spellings:
                for runner in ("bash", "sh", "zsh", "bash.exe"):
                    command = f"echo {shlex.quote(b64)} | {decoder} {spelling} | {runner}"
                    if gate.bash_reason(command) is None:
                        failures.append(f"full check allowed: {command}")
                    elif not gate.names_database_surface(command):
                        failures.append(f"early pass skipped: {command}")
        self.assertEqual(failures, [], "\n".join(failures[:20]))
        self.assertTrue(hasattr(gate, "SHELL_DECODERS"),
                        "the decoder list must have one owner in the gate")

    def test_a_decoder_behind_any_wrapper_never_skips_the_full_check(self):
        """K6, seventh hit (Codex review of a53e5419): `env -i base64 -d | bash` passed.

        _segment_command named the segment "-i": it strips the wrapper, stops on the wrapper's
        option, and rescans only for the programs the full check names. The early pass now
        reads _segment_programs (every program a segment may run, under the same rescan rule).
        Cases come from gate.WRAPPERS, each with an option, plus non-wrapper runners.
        """
        import shlex
        gate = _load_gate()
        b64 = base64.b64encode(f'psql -h {REMOTE} -c "DROP TABLE users"'.encode()).decode()
        prefixes = [f"{w} -x" for w in sorted(gate.WRAPPERS)]
        prefixes += ["sudo -u root", "env -i", "env -u HOME", "FOO=1 env -i", "docker run --rm img",
                     "nice -n 5", "timeout 5", "( env -i"]
        failures = []
        for prefix in prefixes:
            for command in (f"echo {shlex.quote(b64)} | {prefix} base64 -d | bash",
                            f"echo {shlex.quote(b64)} | {prefix} base64.exe -di | sh"):
                if gate.bash_reason(command) is None:
                    failures.append(f"full check allowed: {command}")
                elif not gate.names_database_surface(command):
                    failures.append(f"early pass skipped: {command}")
        self.assertEqual(failures, [], "\n".join(failures[:20]))
        # A wrapped decoder with nothing that runs its output is still not this gate's business.
        for command in ("sudo -u root base64 -d notes.b64", "env -i base64 -d notes.b64 > out.txt"):
            with self.subTest(pass_cmd=command):
                self.assertFalse(gate.names_database_surface(command), command)

    def test_both_walks_stop_at_the_same_program(self):
        """K7, sixth hit (Codex review of 754f5ef6): `deno eval "..." base64 | bash` was refused.

        The rule "this word IS the program; the words after it are its arguments" had two
        copies, one in _segment_command and one in _segment_programs. PR 187 added the bun/deno
        inline-program rule to the first copy only, so the early pass counted deno's positional
        `base64` as a decoder. This test is generated, not a list of instances: for every
        wrapper prefix, every program the gate knows (clients, interpreters, inline bun/deno
        forms, data consumers, printers) and every decoder placed AFTER that program, the
        early pass's program set must not hold the decoder. A rule added to one walk only
        fails here.
        """
        import shlex
        gate = _load_gate()
        prefixes = [""] + [f"{w} -x " for w in sorted(gate.WRAPPERS)]
        prefixes += ["sudo -u root ", "env -i ", "docker run --rm img ", "FOO=1 "]
        programs = sorted(gate._KNOWN_PROGRAMS | gate._PRINTERS | {"cat", "grep", "jq"})
        programs += ["bun -e 'console.log(1)'", "bun --print 'x'", "bun --eval='x'",
                     "deno eval 'console.log(1)'", "deno -e 'x'", "deno eval --ts 'x'"]
        failures = []
        for prefix in prefixes:
            for program in programs:
                for decoder in sorted(gate.SHELL_DECODERS):
                    if program.split()[0] in gate.SHELL_DECODERS:
                        continue
                    tokens = shlex.split(f"{prefix}{program} {decoder}")
                    if decoder in gate._segment_programs(tokens):
                        failures.append(f"{prefix}{program} {decoder}  -> "
                                        f"{gate._segment_command(tokens)[0]!r}")
        self.assertEqual(failures, [], f"{len(failures)} cases:\n" + "\n".join(failures[:20]))


class NonDatabaseCommandsPass(GateCase):
    """Commands that name no database surface are not this gate's business."""

    def pass_cases(self):
        probe = self.script("gh-probe.sh", GH_PROBE)
        return [
            WSL_RATE_LIMIT_LOOP,                                   # 07/11 refusal (a)
            f'wsl.exe -e bash "{wsl_path(probe)}" 2>&1 | tr -d \'\\0\' | grep -v bogus',  # (b)
            f"bash {probe.as_posix()}",
            "git status",
            'echo "$(date)" && git log --oneline -3',
            "for i in 1 2 3; do gh api rate_limit -q .rate.remaining; done",
            "Get-ChildItem -Recurse | Select-Object -First 5",
            "py -3 donectl.py status",
            # Undecidable shapes with no database in sight: left to the classifier.
            'bash -c "$(cat notes.txt)"',
            "echo hi | bash",
            "iex 'Get-Date'",  # an opaque eval naming no database (named limit)
            # Review of 4715bdaa (K7): a decoder's name as DATA is not a decoder.
            "echo base64 | bash",
            "echo openssl | sh",
            "printf 'xxd\\n' | bash",
            # Review of c8b17482 (K7): a runner's printed argument is not a program either.
            "docker run --rm alpine echo base64 | bash",
            "sudo -u root cat base64.txt | sh",
            # Review of 754f5ef6 (K7): an inline program's positional argument is not a program.
            "deno eval \"console.log('')\" base64 | bash",
            "bun -e \"console.log(1)\" xxd | sh",
            "env deno eval \"console.log(1)\" openssl | bash",
        ]

    def test_non_database_commands_pass_in_both_tools(self):
        for tool in SHELL_TOOLS:
            for command in self.pass_cases():
                with self.subTest(tool=tool, command=command):
                    result = self.shell(tool, command)
                    self.assertEqual(result.returncode, 0, f"REFUSED via {tool}: {command}\n"
                                                           + result.stderr)

    def test_database_reads_still_pass(self):
        for tool in SHELL_TOOLS:
            for command in (
                "supabase status",
                'psql -h localhost -c "DROP TABLE scratch"',
                f'psql -h {REMOTE} -c "SELECT count(*) FROM users"',
                "curl https://abcdefghijklmnop.supabase.co/rest/v1/users?select=id",
                "grep -rn psql docs/",
            ):
                with self.subTest(tool=tool, command=command):
                    self.assertEqual(self.shell(tool, command).returncode, 0, command)


class McpAllowListUnchanged(GateCase):
    def test_mcp_behaviour(self):
        cases = [
            ("apply_migration", {"project_id": "p", "query": "CREATE TABLE x();"}, 2),
            ("deploy_edge_function", {"project_id": "p"}, 2),
            ("obliterate_everything", {"project_id": "p"}, 2),
            ("execute_sql", {"project_id": "p", "query": "DROP TABLE x;"}, 2),
            ("execute_sql", {"project_id": "p", "query": "SELECT 1; DROP TABLE x;"}, 2),
            ("list_tables", {"project_id": "p"}, 0),
            ("execute_sql", {"project_id": "p", "query": "SELECT count(*) FROM users;"}, 0),
        ]
        for bare, tool_input, expected in cases:
            with self.subTest(tool=bare, tool_input=tool_input):
                result = self.run_gate(f"mcp__claude_ai_Supabase__{bare}", tool_input)
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_other_tools_untouched(self):
        self.assertEqual(self.run_gate("Read", {"file_path": "x"}).returncode, 0)


class InstallerRegistersEveryMatcher(GateCase):
    """settings.json is gitignored, so the installer is how a machine gets the matchers."""

    def install(self, settings: dict) -> dict:
        hook = self.dir / ".claude" / "hooks" / "PreToolUse" / "supabase_write_gate.py"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("# stand-in\n", encoding="utf-8")
        path = self.dir / ".claude" / "settings.json"
        path.write_text(json.dumps(settings), encoding="utf-8")
        result = subprocess.run([sys.executable, str(INSTALLER)], capture_output=True,
                                text=True, env=self.env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def gate_matchers(settings: dict) -> list[str]:
        return [m.get("matcher") for m in settings["hooks"]["PreToolUse"]
                if any("supabase_write_gate.py" in h.get("command", "") for h in m.get("hooks", []))]

    def test_fresh_install(self):
        got = self.gate_matchers(self.install({}))
        self.assertEqual(sorted(got), sorted(["mcp__.*[Ss]upabase.*", "Bash", "PowerShell"]))

    def real_matchers(self, settings: dict, command: str) -> list[str]:
        return [m.get("matcher") for m in settings["hooks"]["PreToolUse"]
                if any(h.get("command") == command for h in m.get("hooks", []))]

    def installer_command(self) -> str:
        fresh = self.install({})
        return fresh["hooks"]["PreToolUse"][0]["hooks"][0]["command"]

    def test_upgrade_adds_missing_matchers_once(self):
        command = self.installer_command()
        old = {"hooks": {"PreToolUse": [
            {"matcher": m, "hooks": [{"type": "command", "command": command}]}
            for m in ("mcp__.*[Ss]upabase.*", "Bash")]}}
        once = self.install(old)
        twice = self.install(once)
        self.assertEqual(twice, once)
        self.assertEqual(sorted(self.real_matchers(twice, command)),
                         sorted(["mcp__.*[Ss]upabase.*", "Bash", "PowerShell"]))

    def test_a_command_that_is_not_the_installers_is_not_the_gate(self):
        """Reviews of a7ea0f3b and db611864: a lookalike file name and an echo naming the file
        were each taken as installed. Only the installer's own exact command counts."""
        command = self.installer_command()
        for fake in ("python C:/x/not_a_real_supabase_write_gate.py", "echo supabase_write_gate.py"):
            with self.subTest(fake=fake):
                old = {"hooks": {"PreToolUse": [
                    {"matcher": m, "hooks": [{"type": "command", "command": fake}]}
                    for m in ("mcp__.*[Ss]upabase.*", "Bash", "PowerShell")]}}
                got = self.install(old)
                self.assertEqual(sorted(self.real_matchers(got, command)),
                                 sorted(["mcp__.*[Ss]upabase.*", "Bash", "PowerShell"]))

    def test_only_the_exact_entry_the_installer_writes_counts(self):
        """Review of 5b79b600: an entry with the exact command but `"async": true` (which cannot
        block) or `"type": "prompt"` was taken as installed. Installed now means the whole hook
        entry equals the one this installer writes; any other shape gets that entry beside it."""
        command = self.installer_command()
        written = {"type": "command", "command": command}
        for label, shape in {"async": {**written, "async": True},
                             "prompt type": {"type": "prompt", "command": command},
                             "unknown extra key": {**written, "asyncRewake": True}}.items():
            with self.subTest(label):
                old = {"hooks": {"PreToolUse": [{"matcher": m, "hooks": [shape]}
                                                for m in ("mcp__.*[Ss]upabase.*", "Bash", "PowerShell")]}}
                got = self.install(old)
                exact = [m.get("matcher") for m in got["hooks"]["PreToolUse"]
                         if written in m.get("hooks", [])]
                self.assertEqual(sorted(exact), sorted(["mcp__.*[Ss]upabase.*", "Bash", "PowerShell"]))


if __name__ == "__main__":
    unittest.main()
