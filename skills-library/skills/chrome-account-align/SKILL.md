---
name: chrome-account-align
description: Use whenever the Claude-in-Chrome extension reports "Browser extension is not connected" or list_connected_browsers returns empty, before retrying browser work — and when setting up a new machine's Chrome for Claude. Deterministically aligns Chrome's claude.ai login with the Claude Code CLI account via a pinned per-machine Chrome profile.
---

# chrome-account-align — one pinned Chrome profile, always the CLI's account

The Claude-in-Chrome extension registers under whatever account the CHROME PROFILE's
claude.ai session holds. The CLI session only sees extensions registered to ITS account
(`~/.claude.json → .oauthAccount.emailAddress`). With multiple claude.ai accounts and
Chrome profiles, these drift — the fix is a standing per-machine pin, not a per-incident
hunt. Estate doctrine: one Gmail end-to-end per machine ([[feedback-account-alignment]]).

## The contract

Every machine pins ONE Chrome profile in `~/.claude/chrome-align.json`
(`{"profileDir": "Profile 1"}`). That profile's claude.ai login equals the CLI's
`oauthAccount.emailAddress` — signed in once, never touched by other accounts. All
Claude browser work happens in that profile; the other profiles' claude.ai logins
become irrelevant.

## When the extension is invisible

1. Run the aligner: `zsh ~/.claude/skills/chrome-account-align/scripts/align.sh`
   (Windows: `scripts/align.ps1`). No mapping yet → it enumerates profiles with their
   identities and exits with the one-line pin command; run it and re-run the aligner.
2. The aligner opens `claude.ai/chrome` in the pinned profile and prints the contract
   (CLI account vs pinned profile). If the opened page shows a different account,
   switch it there — once; the pin makes it permanent.
3. Wait ~20s, then re-check `list_connected_browsers`. First-ever installs write a
   native-messaging-host file Chrome only reads on startup — a full Chrome quit (⌘Q)
   is REQUIRED then, and restarting Claude Code may be too (per
   code.claude.com/docs/en/chrome). The operator can also run `/chrome` in the CLI →
   "Reconnect extension" (fixes idle service workers; needs extension ≥1.0.36).
4. Still empty after a sign-in-verified attempt + restarts → matches the known
   stale-identity bug (anthropics/claude-code#24593, no official fix); report the exact
   CLI email and pinned profile name to the operator; do not loop.
- **Completion criterion:** `list_connected_browsers` shows a browser, or the mismatch
  is reported with both identities named.

## New machine setup

Run the aligner once (it guides the pin), sign claude.ai in as the CLI account inside
the pinned profile, install the extension there (claude.ai/chrome), fully restart
Chrome. Done — every future session self-heals via the steps above.

## Deeper failure modes

Wrong-MACHINE bind (tools respond but act on another computer's Chrome) and the
stale-relay cleanup recipe live in [[feedback-account-alignment]] — run its
`navigator.platform` check via javascript_tool before trusting a connected browser,
and note some sessions need the `claude --chrome` flag for the tools to load at all.

## Boundaries

The script never reads cookies or stored credentials and never signs in by itself —
sign-in is always the operator's click in the opened tab (credential handling is
prohibited for agents). It only reads profile NAMES/emails from Chrome's Preferences
JSON and the CLI email from `~/.claude.json`, and launches Chrome into the pinned
profile.
