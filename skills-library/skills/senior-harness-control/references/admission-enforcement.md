# Pi-CEO admission enforcement

Pi-CEO has three deployment-controlled modes through
`SENIOR_HARNESS_ADMISSION_MODE`: `off` (default), `observe`, and `enforce`.
Only `enforce` consumes authority. Caller text cannot select the mode.

## Runtime contract

The external Harness reserves a signed parent, derives one signed child per Unlazy leaf, and stores
both through the public PostgREST issuer wrappers installed by
`supabase/migrations/20260821_senior_harness_admissions.sql`. Pi-CEO accepts only a child whose
Ed25519 signature, exact repository, brief digest, scope digest, task, plan, node, reservation,
worker context, 12-character lowercase-hex session ID, base SHA, node-contract digest, audience,
expiry, signer, lineage, and durable database row all agree.

`/api/build` accepts the safe nine-field reservation projection, its matching admission reference,
and a transient `senior_harness_admission_envelope`. The envelope, signature, claim digest, public
key material, and consumer credential are never placed on `BuildSession`, local JSON, Supabase
checkpoints, logs, or API responses. Atomic consume happens before session memory, persistence, or
task scheduling. The literal first build operation reasserts the durable lease. Further assertions
run before model planning, generation, evaluation, adversarial review, and push.

Root `/api/build/parallel` stays denied in enforce mode. The external Harness derives and submits
each admitted leaf separately.

## Resume and recovery

Persisted correlation never restores authority. Local restoration produces inert `interrupted`
sessions, and automatic Supabase resume is disabled in enforce mode. Explicit resume requires a new
child bound to the existing exact session ID plus the exact resume brief, scope, reservation, and
current workspace HEAD. A consumed, revoked, released, or expired child is never replayed.

## Deployment configuration

Production `enforce` requires all of the following before server startup:

- `SENIOR_HARNESS_ADMISSION_RPC_URL`: credential-free HTTPS PostgREST URL ending in `/rest/v1/rpc`.
- `SENIOR_HARNESS_ADMISSION_CONSUMER_TOKEN`: a dedicated consumer-role token, never a Supabase
  service-role key. Startup reads it once and removes it from `os.environ` before background work.
- `SENIOR_HARNESS_ADMISSION_PUBLIC_KEYS`: JSON object mapping signer key IDs to base64url Ed25519
  public keys.
- `SENIOR_HARNESS_ADMISSION_REVOKED_KEY_IDS`: JSON array of revoked key IDs; default `[]`.
- `SENIOR_HARNESS_ADMISSION_AUDIENCE`: the deployment's base audience, for example `pi-ceo/build`.
- Provisioned `senior_harness_issuer` and `senior_harness_consumer` database roles with only the
  migration's exact function grants, plus an external private signing key that Pi-CEO cannot read.

Startup fails closed when any enforce configuration is absent or malformed. `off` and `observe`
remain backward-compatible and do not require these values.

## Promotion gate

Local tests do not authorize production enablement. Require a live accepted-child smoke, immediate
replay denial, revoke/expiry denial, fresh-child resume for the same session, exact base checkout,
consumer-token absence from an SDK child environment, and current exact-SHA review evidence before
changing a deployment from `observe` to `enforce`.
