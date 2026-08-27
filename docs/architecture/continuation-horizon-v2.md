# Mission Control continuation horizon v2

The continuation horizon is a control-plane primitive, not a chat-memory feature.

## Contract

- one root objective remains stable until verified complete
- follow-up Telegram/Slack/Mission Control instructions refine the root objective rather than replacing it
- up to 15 concrete next moves are maintained and dependency-safe moves may proceed in parallel
- protected actions remain gated and must not stall unrelated safe work
- Supabase is the durable cross-machine source of truth when configured
- an atomic local JSON file remains the fail-soft hot cache
- public clients receive no direct table access; the service-role backend owns persistence
- completion requires evidence and explicitly disarms continuation

## Rollout

1. merge code and schema migration file
2. apply the migration in the controlled production migration lane
3. verify service-role read/write and local fallback
4. verify a Telegram follow-up preserves the root objective
5. verify another machine/process reads the same horizon
6. expose read-only horizon state in Mission Control
