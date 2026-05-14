# Hermes Plugins (Pi-Dev-Ops mirror)

Canonical git-tracked source for Hermes plugins that Phill authors locally.
These plugins live at `~/.hermes/plugins/<name>/` at runtime — Hermes loads
them automatically on gateway start. They are **not** under any git repo at
that location, so a `hermes update` reset, an accidental `rm -rf ~/.hermes`,
or moving to a new Mac would lose every plugin fix.

This directory mirrors the plugin tree so the work survives. The deploy
script keeps the two in sync.

## Plugins under management

| Plugin | Purpose |
|---|---|
| `unite-group/` | Supabase + Linear data fetchers for the Unite-Group portfolio (portfolio_health, ccw_kpis, wave_status, 6pager_summary). Tools called by Hermes when Phill asks empire questions. |

## Sync workflow

After editing a plugin **in either location**, run the sync script in the
direction that matches the change:

```bash
# Copy local → repo (after fixing a plugin under ~/.hermes/plugins/ and
# wanting to commit the change)
./scripts/sync-hermes-plugins.sh pull

# Copy repo → local (after pulling a teammate's commit, or after a fresh
# Hermes reinstall that wiped ~/.hermes/plugins/)
./scripts/sync-hermes-plugins.sh push
```

Either direction respects existing file timestamps and prints a diff
summary so a stray local edit isn't silently overwritten.

## History note

2026-05-14: All four `_handle_ug_*` tool handlers in `unite-group/tools.py`
got a `**_kwargs` parameter to accept (and ignore) the `task_id` kwarg the
Hermes dispatcher passes. Was causing recurring `TypeError` warnings in
gateway logs every time an empire-status tool fired. Fix committed here as
the canonical source after surfacing during the 2026-05-14 Hermes audit.
