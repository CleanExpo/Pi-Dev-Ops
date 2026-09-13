# Schema Drift database connection (Mission Control)

Mission Control shows whether the Pi-Dev-Ops API can reach the database that the Schema
Drift check reads. The component is called `schema_drift_db`. It appears in two places:
- `GET /api/health/full`, under `components.schema_drift_db`
- the observability panel of `GET /api/mission-control/live`

The probe lives in `app/server/schema_drift_db.py`. It opens one Postgres connection with
`SUPABASE_DB_URL` and runs the Schema Drift workflow's own catalog query
(`.github/workflows/schema_drift.yml`).

## What it reports

| Status | `observed` | `ok` | Meaning |
|---|---|---|---|
| `live` | true | true | Connected. The note says how many public tables the login can see. |
| `not_observed` | false | false | `SUPABASE_DB_URL` is unset, `psycopg` is missing, or no database answered (unreachable, timed out, or a malformed URL). Mission Control lists it as degraded, never green. |
| `red` | true | false | A database answered but refused the login, the catalog query failed, or the catalog listed 0 public tables. |

`health_full` gives each component 2 seconds. A slower probe is reported as `error: timeout`, never as ok.

The result is cached for 60 seconds per process, so polling opens at most one connection a
minute. The login's connection limit is 3.

## The variable: `SUPABASE_DB_URL`

- **One variable.** It is the name the Schema Drift workflow already uses for its GitHub Actions secret, so both consumers read the same credential under the same name.
- **Fail-closed.** When it is unset, the component reads `not_observed`, never `ok`.
- **Never echoed.** Payloads carry fixed text only.
  - Driver error text includes the host and user, and can quote the connection string itself.
  - The probe therefore classifies an error and then discards its text.
  - Do not paste the value into chat, tickets or logs.

## Connection form: shared pooler, session mode

```text
postgresql://schema_drift_ro.<PROJECT-REF>:<PASSWORD>@aws-<N>-<REGION>.pooler.supabase.com:5432/postgres?sslmode=require
```

Source: Supabase, [Connect to your database](https://supabase.com/docs/guides/database/connecting-to-postgres), read 13/09/2026.

**Why the session pooler**
- Mission Control's API is a persistent backend: a long-running container on Railway (`railway.toml`, Dockerfile builder).
- Supabase's guide sends a persistent backend to one of two forms:
  - a **direct connection**, when the backend is on IPv6 or the project has the IPv4 add-on
  - the **shared pooler in session mode**, when the backend is on an IPv4-only network ("The shared pooler is IPv4-only on every plan.")
- The direct host, `db.<PROJECT-REF>.supabase.co:5432`, is IPv6 unless the IPv4 add-on is enabled.
- Whether Railway's egress reaches IPv6 was not checked (UNVERIFIED). The session pooler works either way.
- It is also the exact form Schema Drift run [34753874496](https://github.com/CleanExpo/Pi-Dev-Ops/actions/runs/34753874496) connected with.

**Why not transaction mode (port 6543):** the guide reserves it for serverless and edge functions, and it does not support prepared statements.

**Getting the details right**
- Through the shared pooler, a custom role's username is `[ROLE].[PROJECT-REF]`.
- Take the pooler host from the Dashboard's **Connect → Session pooler**. The guide says it "can't be composed from your region".

**No existing form to match.** Until now, Mission Control reached Supabase only over REST (`app/server/supabase_log.py`, `SUPABASE_URL` plus the service-role key). This is its first Postgres-protocol connection, so it matches the Schema Drift workflow's form instead.

## Least-privilege login

```sql
-- schema-drift-role: tests/test_schema_drift_db_pg.py runs this block on an ephemeral Postgres
create role schema_drift_ro login noinherit connection limit 3 password 'GENERATED_PASSWORD';
alter role schema_drift_ro set default_transaction_read_only = on;
alter role schema_drift_ro set statement_timeout = '15s';
```

- **No `GRANT` at all.** The only query reads `pg_class` and `pg_namespace`, which Postgres makes readable by `PUBLIC`.
- **No inherited power.** `NOINHERIT`, a member of no roles, and not superuser, createrole, createdb or bypassrls (the defaults).
- **Limits.** Read-only by default, a 15-second statement timeout, and at most 3 connections.

Proof query, run as an admin. It must return `0` for the login and a positive number for the owner:

```sql
select count(*) filter (where has_table_privilege('schema_drift_ro', c.oid, 'SELECT')) as login_tables,
       count(*) filter (where has_table_privilege('postgres', c.oid, 'SELECT'))        as owner_tables
from pg_class c join pg_namespace n on c.relnamespace = n.oid
where n.nspname = 'public' and c.relkind = 'r';
```

**Pi CEO already has this login.**
- It was created on 13/09/2026 by a founder-run script through the Supabase Management API.
- That script sent a SCRAM verifier instead of a plain password, so the password never left the Mac.
- On that run, the login could SELECT 0 of 69 public tables.
- Do not re-create it, and do not run SQL against production to "check" it.

## The one manual step (Phill)

Set `SUPABASE_DB_URL` on Railway: project **Pi-Dev-Ops**, environment **production**, service **Pi-Dev-Ops**.

**Why this step also sets a new password.** The current password exists only inside the GitHub secret, and GitHub secrets cannot be read back. So the step gives `schema_drift_ro` a new password and writes the new string to both GitHub and Railway in one run, without printing it.

**How.** Phill runs a local helper script. It is kept outside this public repo because it uses the Supabase owner token. Before it saves anything, it checks two things:
- the login can read 0 tables
- a wrong password is refused

Its Railway write is:

```bash
printf '%s' "$URL" | railway variable set SUPABASE_DB_URL --stdin --service Pi-Dev-Ops --environment production
```

- Setting a variable redeploys the service.
- **Done** when `GET /api/health/full` shows `components.schema_drift_db.status` = `live`.
- **Undo** the Railway half by deleting the variable in Railway → Pi-Dev-Ops → Variables. The component returns to `not_observed`.

## Tests (D19: ephemeral Postgres only)

**`tests/test_schema_drift_db.py`** runs in the normal pytest job.
- Covers: unset, unreachable, malformed, refused, a crashing probe, the table-count verdict, and the cache.
- Plants canary values in the URL and checks that none appear in the payload.
- First proves the driver's raw error does contain them, so an absent canary means something.

**`tests/test_schema_drift_db_pg.py`** runs in the `rls-assertions` job, against its `pgvector/pgvector:pg15` service container.
- Creates the login from the SQL block above and connects through the probe.
- Confirms the login is read-only and cannot read rows.
- Confirms a wrong password reads red and echoes nothing.
- Refuses a non-local `SCRATCH_DB_URL`, and never uses a remote database or `SPINE_DATABASE_URL`.
- Fails, rather than skips, when the job sets `SCHEMA_DRIFT_DB_PG_REQUIRED=1`.

Local run:

```bash
docker run -d --rm --name sddb -e POSTGRES_PASSWORD=shadow -e POSTGRES_DB=pilot_shadow -p 127.0.0.1:55439:5432 pgvector/pgvector:pg15
SCRATCH_DB_URL=postgres://postgres:shadow@127.0.0.1:55439/pilot_shadow SCHEMA_DRIFT_DB_PG_REQUIRED=1 python -m pytest tests/test_schema_drift_db_pg.py -v
docker stop sddb
```
