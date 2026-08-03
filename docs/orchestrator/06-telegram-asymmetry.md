# Telegram — asymmetric by construction

**Bot:** `PiCeoEmpire_Bot` · **Token:** BotFather → founder-supplied, never in this repo.

The bot sends you everything. It accepts nothing that spends money or touches production.

---

## The thing to understand before installing anything

The **official Anthropic Telegram plugin is bidirectional.** It exists to turn a Telegram DM into a
Claude Code instruction — that is its whole purpose. Installing it does not create a one-way channel;
it creates an inbound command path into a machine that has `Bash(*)` and `Write(*)`.

So the asymmetry cannot come from the plugin. **It comes from the fence**, which does not care where an
instruction came from:

| Message | Origin | Outcome |
|---|---|---|
| "deploy to prod" | keyboard | refused — production |
| "deploy to prod" | Telegram DM | refused — production, *by the identical rule* |
| "buy more credits" | Telegram DM | refused — spend |
| "delete the HARD_STOP" | Telegram DM | freezes on first attempt — self-modification |

**The inbound restriction is a property of the fence, not of the chat integration.** That is the right
place for it: one rule, enforced once, regardless of channel. It also means the restriction holds for
channels nobody has thought of yet.

**Consequence: do not install the inbound plugin before the fence is installed.** In that order it is a
remote command channel into an ungated machine.

## Outbound — `fence/notify.py`

Send-only. No inbound path, no command parser, no way to act on a reply.

It takes a **kind** (`incident` | `drift` | `brief`) and a **path to a fence-generated file**. There is
no free-text argument, so an agent cannot use it to send arbitrary content — it can only cause an
artifact the fence itself wrote to be delivered.

If the token is absent it **says so on stderr and exits 3**. It never exits 0 having sent nothing —
a notifier that silently no-ops is worse than none, because the silence reads as "nothing happened."

## Releasing a frozen agent is a desktop action

When the fence trips, it writes `~/.claude/HARD_STOP`. While that file exists, every tool call is
refused — including reads.

Release means deleting that file. That is deliberately **not** possible from Telegram:

1. `**/HARD_STOP` is on `self_modification_globs`, so an agent attempting it freezes on the first try.
2. The agent is already frozen, so it cannot act on any instruction anyway.
3. Deletion therefore requires a human at the filesystem.

A phone can tell you the agent is frozen. It cannot un-freeze it.

## Known weakness — state it, don't hide it

Anyone paired to the bot can cause a freeze: DM something that hits the fence twice, and the agent stops.
That is a denial-of-service, not a breach — the failure direction is *stopped*, which is the safe one.

Mitigation is the plugin's own allowlist (pair, then switch off pairing-code replies). Worth doing before
the bot is given to anyone but the founder.

## Founder step — one time, cannot be done by an agent

```
1. BotFather → /newbot (or /token for PiCeoEmpire_Bot) → copy the token
2. DM the bot once, then read the chat id
3. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
     - locally: environment variables
     - CI:      repo secrets (drift check reads them)
```

Until this is done the fence still freezes, still writes incident notes to disk, and the drift check
still runs and still fails the build. **You just don't get pinged.** Nothing depends on Telegram for
enforcement — it is notification only, by design.
