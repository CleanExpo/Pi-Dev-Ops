# Sign-in cards: Claude, Codex, Cursor (RA-8192, AR-06)

**HUMAN ONLY. Phill signs in. Agents never run these commands.**

These cards are for you, Phill, when the Ops Board shows a seat as `auth_expired`, or when you decide to move a seat to another account. Each card is one machine and one tool: check, sign in, check again. It takes about two minutes.

Why only you: signing in picks which paid account a machine uses. The account router (AR-01 to AR-06) pins one account per machine and never signs in, signs out or swaps accounts by itself, so it can never stack quotas or move spend without you.

Commands on these cards were read from each tool's own `--help` on the Mac mini on 5 Nov 2026: Claude Code 2.1.318, Codex CLI 0.166.0, Cursor Agent 2026.10.22. They were not run, and they were not checked on the MacBook or PC. If a command there says "unknown command", update that tool first and tell the lane, so this page gets fixed.

<a id="state-to-card"></a>

## Which card do I need?

The Ops Board and the night-queue picker use the same five state words from the HEADROOM log (`docs/headroom-events.md`).

| State | What it means | Who acts | Go to |
|---|---|---|---|
| `auth_expired` | The login is dead. Nothing runs on that seat until you sign in again. | You | `card-<provider>-<machine>`, for example [Claude on the Mini](#card-claude-mini), [Codex on the Mini](#card-codex-mini), [Cursor on the PC](#card-cursor-pc) |
| `5h_cooling` | The short usage window is used up. It comes back by itself. | Nobody | [Wait it out](#wait-it-out) |
| `weekly_cooling` | The weekly allowance is used up. It comes back by itself. | Nobody | [Wait it out](#wait-it-out) |
| `billing_blocked` | The plan itself blocks use. Signing in again will not fix it. | You decide | [Plan or spend decision](#plan-or-spend-decision) |
| `on_demand_capped` | Included usage is gone; more would cost money. | You decide | [Plan or spend decision](#plan-or-spend-decision) |

The Ops Board links a row to `#card-<provider>-<machine>` on this page, where provider is `claude`, `codex` or `cursor` and machine is `mini`, `macbook` or `pc`.

<a id="before-you-start"></a>

## Before you start (every card)

1. Open the account map, `ops/ACCOUNT-MAP.yaml` (it lands with RA-8187). Find the account label for this tool and machine, for example `claude-mini`. That label tells you which account to sign in with. The map is the only place the account is written down; this page never names an email.
2. Sit at that machine, or open a screen-share to it. Sign-in opens a browser on the machine itself.
3. Have the account's password and two-step code ready.

If the map pins no account for that tool on that machine, stop: nothing should sign in there. Changing the map is your decision, made separately.

<a id="card-claude"></a>

## Claude

**HUMAN ONLY. Phill signs in. Agents never run these commands.**

Uses your Claude subscription (Max). The sign-in below uses the subscription by default. Account: the `claude-<machine>` label in `ACCOUNT-MAP`.

<a id="card-claude-mini"></a>

### Claude on the Mac mini

Open Terminal on the Mac mini.

```bash
claude auth status --text
claude auth login
claude auth status --text
```

1. The first line shows who is signed in now, or that nobody is.
2. `claude auth login` opens the browser. Sign in with the account for `claude-mini`.
3. The last line should now show that account. If it does not, sign in again; do not hand it to an agent.

Inside a running Claude Code window, typing `/login` does the same thing.

<a id="card-claude-macbook"></a>

### Claude on the MacBook

Open Terminal on the MacBook. Same steps as the Mini, with the `claude-macbook` account.

```bash
claude auth status --text
claude auth login
claude auth status --text
```

<a id="card-claude-pc"></a>

### Claude on the PC

Open PowerShell on the PC. Same steps, with the `claude-pc` account. The PC's plan is still undecided (RA-8195); if the map has no plan for it yet, stop at step 1 of "Before you start".

```powershell
claude auth status --text
claude auth login
claude auth status --text
```

<a id="card-codex"></a>

## Codex

**HUMAN ONLY. Phill signs in. Agents never run these commands.**

Uses your ChatGPT Pro account. Account: the `codex-<machine>` label in `ACCOUNT-MAP`.

If a job stopped on "Your workspace is out of credits", that is a dead Codex login, not billing. Sign in again with this card; nothing needs to be bought. "unexpected status 401 Unauthorized" means the same thing: no valid Codex login.

While the Mini's Codex login is dead, reviews fail over to the MacBook by themselves (`docs/codex-failover.md`). That keeps work moving; it does not sign the Mini back in. Only this card does.

<a id="card-codex-mini"></a>

### Codex on the Mac mini

Open Terminal on the Mac mini.

```bash
codex login status
codex login
codex login status
```

1. The first line shows whether Codex is signed in.
2. `codex login` opens the browser. Sign in with the account for `codex-mini`. If you are on a screen-share and the browser does not open, use `codex login --device-auth` instead: it prints a short code to enter on any browser.
3. The last line should now say you are signed in with ChatGPT.

<a id="card-codex-macbook"></a>

### Codex on the MacBook

Only if the map pins a Codex account to the MacBook. Open Terminal there. Same steps as the Mini, with the `codex-macbook` account.

```bash
codex login status
codex login
codex login status
```

<a id="card-codex-pc"></a>

### Codex on the PC

Only if the map pins a Codex account to the PC. Open PowerShell there. Same steps, with the `codex-pc` account.

```powershell
codex login status
codex login
codex login status
```

<a id="card-cursor"></a>

## Cursor

**HUMAN ONLY. Phill signs in. Agents never run these commands.**

Uses your Cursor plan, through the `agent` command (also installed as `cursor-agent`). Account: the `cursor-<machine>` label in `ACCOUNT-MAP`. A second Grok seat waits on RA-8193; there is no card for it until that is decided.

<a id="card-cursor-mini"></a>

### Cursor on the Mac mini

Open Terminal on the Mac mini.

```bash
agent status
agent login
agent status
```

1. The first line shows who is signed in.
2. `agent login` opens the browser. Sign in with the account for `cursor-mini`. On a screen-share with no browser, run `NO_OPEN_BROWSER=1 agent login` and open the link it prints.
3. The last line should now show that account.

<a id="card-cursor-macbook"></a>

### Cursor on the MacBook

Open Terminal on the MacBook. Same steps as the Mini, with the `cursor-macbook` account.

```bash
agent status
agent login
agent status
```

<a id="card-cursor-pc"></a>

### Cursor on the PC

Open PowerShell on the PC. Same steps, with the `cursor-pc` account.

```powershell
agent status
agent login
agent status
```

<a id="after-you-sign-in"></a>

## After you sign in

- The night-queue picker keeps skipping that machine for up to 12 hours after the dead-login line was logged, then tries it once more. Signing in does not clear that hold early; that is a known gap, logged on RA-8192.
- The Ops Board keeps showing `auth_expired` for the same window, because it uses the picker's hold rules.
- Nothing else to do. Do not paste a password, code or token into a chat, ticket or agent.

<a id="seat-change"></a>

## Moving a seat to another account

This is your call, never an agent's. First change the account label in `ops/ACCOUNT-MAP.yaml` (MacBook seat RA-8196 and PC billing RA-8195 are waiting on you). Then, at that machine, sign the old account out and the new one in, and check:

```bash
claude auth logout
claude auth login
claude auth status --text
```

Use `codex logout` then `codex login`, or `agent logout` then `agent login`, for the other tools.

<a id="wait-it-out"></a>

## Wait it out

`5h_cooling` and `weekly_cooling` end by themselves at the reset time the board shows. Do not sign out and into another account to get round them: that is quota stacking, and the router rule forbids it.

<a id="plan-or-spend-decision"></a>

## Plan or spend decision

`billing_blocked` and `on_demand_capped` are not sign-in problems. They need a decision from you about the plan or a spend limit (paid overflow is RA-8194, waiting on your GO). Signing in again will not change them.

<a id="never-use"></a>

## Never use these

These turn a subscription sign-in into a metered or key-based login. The estate runs on account sign-ins only.

- `claude auth login --console` (Anthropic Console, API billing)
- `codex login --with-api-key` or `--with-access-token`
- any `*_API_KEY` or token piped into a login command
