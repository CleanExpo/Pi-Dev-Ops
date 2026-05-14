"""swarm.inbox — ContextBot inbound message pipeline.

Reads the `context_bots` registry, long-polls each intake-enabled bot,
files received messages to Linear + the wiki, and dedupes via
`context_bot_messages.telegram_update_id`. Bot identity carries the
routing context — zero NLP needed for classification.
"""
