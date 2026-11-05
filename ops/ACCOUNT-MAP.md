# Account map: how to edit it

`ops/ACCOUNT-MAP.yaml` says which subscription login is used on which computer. The night
queue reads it so each job runs on a machine whose account still has room, instead of
hitting a limit. (RA-8187. The router that reads it comes in later tickets.)

## The rules

- **Emails only.** Never put a password, token, cookie, API key or login code in this file.
  The check fails the build if it sees one.
- **Phill fills the emails. Agents never do.** An agent may run the check and report what it
  says. It must not add, change or guess an email, even if it can see which account is signed
  in on a machine. Which login sits where is Phill's decision.
- **One Claude login per computer.** Each machine has exactly one Claude account pinned.
- **No sharing a Claude login between computers.** If two machines show the same Claude email,
  the check fails, because both would burn one shared limit while the router thinks there are
  two. If you ever want a shared seat on purpose, say so and we change this rule in a reviewed
  PR.

## How Phill edits it

1. Open `ops/ACCOUNT-MAP.yaml`.
2. Find the account, for example `claude-mini`.
3. Replace the placeholder email (it ends in `@pending.invalid`) with the real login email.
4. If you know the plan, set `plan:` (for example `max`). Leave it as `null` if not decided.
5. Save. Ask an agent to open the PR, or open it yourself. The PR's checks run the validator.

Placeholders are allowed. They show as `PENDING` in the check output so nobody mistakes them
for a real mapping.

## What each field means

| Field | Meaning |
|---|---|
| `label` | Short unique name, e.g. `claude-mini`. Other tools key on it. |
| `provider` | `claude`, `codex` or `cursor`. Nothing else: other providers are API-key lanes, which are not used. |
| `plan` | The subscription plan, or `null` while undecided. |
| `email` | The login email. Placeholder ends in `.invalid`. |
| `machines` | Which computers use this login, by machine `id`. |
| `notes` | Plain notes. No secrets here either. |

Machines are listed at the top under `machines:` with an `id`, an optional `host` (the
computer's short name) and notes.

## Running the check

```bash
python3 scripts/check_account_map.py                 # passes with placeholders, lists them as PENDING
python3 scripts/check_account_map.py --require-real  # fails until every email is real
```

It only reads the file. It never changes it, never signs in, and never touches any account.

## Open decisions that change this file

- MacBook seat: RA-8196
- PC payment: RA-8195
- Second Grok account: RA-8193 (Grok is not a provider in this map yet)
