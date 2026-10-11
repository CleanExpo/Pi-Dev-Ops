> Moved from SKILL.md. Read when closing out or re-verifying the env-puller implementation.

## Verification (Wave 5 #2 close-out)

1. **Manifest schema lint** — every manifest validates against `.harness/env-manifests/manifest.schema.json`.
2. **Refresh dry-run** — run `scripts/refresh_env_manifest.py --slug pi-dev-ops --dry-run`, verify diff output names new vars without values.
3. **Resolve smoke** — call `resolve_for_run(project_slug="pi-dev-ops", run_id="smoke-1")` → returned dict has the expected names; config file exists at `/dev/shm/sandcastle-config-smoke-1.json` (mode 0600); after `os.unlink`, file gone; `audit_emit` row written with `var_names` array but NO values.
4. **Skip-pattern enforcement** — synthetic manifest with `NEXT_PUBLIC_TEST_KEY` → resolve filters it out; not in returned dict.
5. **Cross-project isolation** — call `resolve_for_run(project_slug="restoreassist")` then `resolve_for_run(project_slug="synthex")` in the same Pi-CEO process → returned dicts share no overlapping non-public keys (tested by intersection).
6. **Auth-failure escalation simulation** — feed a synthetic Sandcastle log_tail containing `401 Unauthorized` → verify `cfo_alert` audit row + draft posted via draft_review (TEST_MODE) within 60 s.
7. **Secret-leak grep over all artefacts**:
   ```
   grep -RE '(?:[A-Z_]{4,}_(?:KEY|TOKEN|SECRET|PASSWORD))[^A-Z_]+[A-Za-z0-9/+=]{16,}' \
     .harness/swarm/swarm.jsonl \
     .harness/env-manifests/ \
     /tmp/pi-ceo-workspaces/sandcastle/
   ```
   → must return ZERO matches across 10 consecutive smoke runs.
