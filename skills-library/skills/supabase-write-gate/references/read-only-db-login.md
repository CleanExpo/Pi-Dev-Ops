# Read-only database login for agents (one per project)

**Status: prepared, NOT created.** Creating a database login is a credential change, so
Phill does these steps (or a session he authorises for that one project). Agents never run
them and never create a login themselves (grill 18 no-go, 07/11/2026).

## Contents

- [Why](#why)
- [Order](#order)
- [Steps for one project](#steps-for-one-project-about-10-minutes)
- [Check it](#check-it-watch-each-refusal-happen)
- [Undo](#undo)
- [After it exists](#after-it-exists)
- [Record per project](#record-per-project)

## Why

The write gate (`hooks/PreToolUse/supabase_write_gate.py`) reads command text. Text checks
cannot see a database reached through an environment variable, a script the gate cannot
open, or a user-defined function that writes (named limits in that file). A login that
the database itself refuses to let write closes all three, and it does not go out of date
when the gate does. Agents then connect with this login for every read.

## Order

1. **RestoreAssist production first** (the 28/07/2026 incident project).
2. Then each other Supabase project agents read: Unite-Group, CARSI, Synthex, and the rest
   listed by `list_projects`. One login per project; never share one across projects.

## Steps for one project (about 10 minutes)

Source for the role recipe: Supabase's own help article
<https://supabase.com/kb/troubleshooting/pg_dump-fails-with-query-would-be-affected-by-row-level-security-policy>
(retrieved 07/11/2026). Login name format: <https://supabase.com/docs/guides/database/prisma>
and <https://supabase.com/blog/postgres-roles-and-privileges>.

1. **Make the password in the password manager.** Generate a long random password and save
   it as `supabase-<project>-agent-readonly`. Do not paste it into a chat, a ticket or a file.
2. **Open the project's SQL editor** in the Supabase dashboard (signed in as the owner).
3. **Create the login.** Replace `<password from the password manager>` in the editor only:

   ```sql
   CREATE ROLE agent_readonly LOGIN PASSWORD '<password from the password manager>' BYPASSRLS;
   GRANT pg_read_all_data TO agent_readonly;
   ALTER ROLE agent_readonly SET default_transaction_read_only = on;
   ```

   - `pg_read_all_data` gives SELECT on every table and nothing else: no INSERT, UPDATE,
     DELETE, CREATE or sequence change. It exists from PostgreSQL 14; check first with
     `SHOW server_version;`. On an older project use this instead of that line, once per
     schema agents read (`public` shown):

     ```sql
     GRANT USAGE ON SCHEMA public TO agent_readonly;
     GRANT SELECT ON ALL TABLES IN SCHEMA public TO agent_readonly;
     ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT ON TABLES TO agent_readonly;
     ```
   - `default_transaction_read_only = on` makes every session start read-only, a second wall.
   - `BYPASSRLS` lets it see every row, as an admin read would. It does not grant any write.
     Leave the word out if agents should see only what row policies allow (most policies
     name `authenticated` or `anon`, so the login would then see few or no rows).
4. **Remove anything it should not run.** Functions are executable by everyone by default,
   and a `SECURITY DEFINER` function runs with its owner's rights, so it can write. List them:

   ```sql
   SELECT n.nspname, p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog', 'information_schema');
   ```

   For each one that writes and agents must not call:
   `REVOKE EXECUTE ON FUNCTION <schema>.<name>(<args>) FROM PUBLIC;` then grant it back to
   the app roles that need it. If that would break the app, leave it and record the
   function name below as a remaining limit.
5. **Store the connection string** in the credential store the estate already uses
   (`skills/library/connections.md`, found by `bin/find-cred`), as
   `postgres://agent_readonly.<project-ref>:<password>@<region>.pooler.supabase.com:5432/postgres`.
   Never in a repo, a `.env` that is committed, or a prompt.

## Check it (watch each refusal happen)

Connect with the new login (`psql "<string from the credential store>"`) and run:

| Statement | Expected |
|---|---|
| `SELECT current_user;` | `agent_readonly` |
| `SELECT count(*) FROM "User";` (any real table) | a number |
| `CREATE TABLE agent_probe (x int);` | ERROR: permission denied (or read-only transaction) |
| `INSERT INTO "User" DEFAULT VALUES;` | ERROR: permission denied |
| `BEGIN; SET TRANSACTION READ WRITE; UPDATE "User" SET id = id WHERE false; ROLLBACK;` | ERROR: permission denied |

All three writes must fail. If any succeeds, undo the login (below) and stop.

## Undo

```sql
REASSIGN OWNED BY agent_readonly TO postgres;
DROP OWNED BY agent_readonly;
DROP ROLE agent_readonly;
```

Then delete the password manager entry and the stored connection string.

## After it exists

- Agents use this login for database reads in that project; the owner login stays with Phill.
- Once a project's login is checked, a later PR may cut more of the gate's shell rules for
  that project, with a test that proves the database refuses an agent write. Not before.

## Record per project

| Project | Created (date, by) | Check passed | SECURITY DEFINER functions left callable |
|---|---|---|---|
| RestoreAssist production | not yet | - | - |
