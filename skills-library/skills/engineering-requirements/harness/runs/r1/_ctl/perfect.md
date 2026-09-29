
lib/sync-queue.ts writes nextAttemptAt in incrementRetry and drainQueue never reads it,
so the backoff is not enforced. getSyncStatus returns SYNCED while failed entries exist,
because failed is counted by neither branch and is therefore never surfaced to the user.
lib/notify.ts sendEmail is void and swallows every error, yet runWatchdog sets alerted
unconditionally, so the record is always true. In 002_policies.sql the "Anon read access"
policy is USING (true) and anon holds a GRANT, so every row of reports is readable.
lib/schema.prisma cascades from User through Inspection to AuditLog, so deleting a user
destroys the audit trail. 003_rls_fix.sql is committed but absent from the ledger and was
never applied. vitest.config.ts include globs do not match __tests__/engine.test.ts, so it
never runs. app/api/health/route.ts falls back to a hardcoded version, so the endpoint
cannot identify the running build.
