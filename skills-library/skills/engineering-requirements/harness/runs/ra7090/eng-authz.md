by: eng-authz
contributed: [eng-authz]
categories:
  invariants:    {state: PRESCRIBED, ref: "#every-tenant-owner-is-role-admin", by: eng-authz, blocking: true}
  failure_modes: {state: PRESCRIBED, ref: "#signed-urls-are-minted-for-unverified-object-paths", by: eng-authz, blocking: true}
  test_oracle:   {state: PRESCRIBED, ref: "#the-tenancy-tests-bless-the-bypass", by: eng-authz}
cross_domain:
  - "DeviceSigningKey.userId is onDelete: Cascade, so deleting an offboarded user destroys the public keys every historical manifest they signed needs — the parent-dies question is eng-data's"
  - "storage.objects SELECT policy is `TO authenticated USING (bucket_id = 'evidence-optimised')` with no org predicate — eng-secrets owns whether an anon-key surface can ever reach that bucket"
  - "the custody export's 500-event page + COUNT runs per request against an unbounded CustodyEvent table — eng-performance owns the read cost"

## every tenant owner is role admin

The change under review is RA-7090 (device-signed native capture, custody export). Per method §3 this finding is about the **foundation**, not the feature: the feature is sound, and it is bolted onto a tenancy check that does not isolate tenants. RA-7090 raises the blast radius of that foundation from "another tenant's report row" to "another tenant's original photographic evidence bytes, GPS, capturing user, device key and full custody chain".

The spec states the invariant [VERIFIED] `spec.md:49`:

> All access is organisation-isolated. Role is enforced server-side on every write; JWT role claims are re-validated against the database for privileged actions.

The re-validation half is honoured. The isolation half is not. Concretely:

1. Every self-registration is minted as `ADMIN` [VERIFIED] `app/api/auth/register/route.ts:135,144` — `// All registrations create an ADMIN user with their own organisation` / `role: "ADMIN",`. Same value in `app/api/auth/google-signin/route.ts:177` and `app/api/auth/native-token-exchange/route.ts:290`. There is no platform-admin allowlist anywhere (`grep -rn "PLATFORM_ADMIN\|isPlatformAdmin\|ADMIN_EMAILS" lib app` returns nothing).
2. `Role` has three values [VERIFIED] `prisma/schema.prisma:886-890` — `enum Role { USER ADMIN MANAGER }`. So the *tenant-owner* role and the *platform-operator* role are one value. This is the membership-vs-capability failure exactly: the check asks "are you an ADMIN", never "an ADMIN of which organisation, over which object".
3. The admin branch of the shared tenancy helper drops the tenant predicate entirely [VERIFIED] `lib/auth/assert-tenancy.ts:98-99` — `const insp = await prisma.inspection.findUnique({` / `where: { id: inspectionId },`. Same shape at `:66` for reports and `:165` for writes.

Scenario, no timing or race required: a person signs up for a free trial (they are now `ADMIN`), obtains one `inspectionId` + `evidenceId` — from a forwarded dashboard URL, a support thread, a shared report link, a portal email — and calls `GET /api/inspections/{id}/evidence/{evidenceId}/custody`. `assertInspectionTenancy` returns `ok` on the admin branch, and the route returns the custody document *plus* `X-Original-Asset-Url`, a one-hour signed URL to the private original in `evidence-originals`, for a claim belonging to a different restoration company. cuids are not guessable in bulk, but one leaked id is total, and the same branch already exposes the evidence list, media and sketch routes.

And the database enforces none of it. My seat's question — which role does the request execute as, and is that role's authorisation enforced by the database — is answered in the repo itself [VERIFIED] `prisma/migrations/20260614000000_ra_4956_tenant_scoped_rls_policies/migration.sql:10-11`:

> `--   for anon/authenticated. Server code (Prisma via DATABASE_URL = postgres`
> `--   superuser, BYPASSRLS; and SUPABASE_SERVICE_ROLE_KEY) is unaffected.`

Every RLS policy across the 119 tables is inert on every application path, by design, and the Supabase client is the service role [VERIFIED] `lib/supabase-server.ts:15` — `const key = process.env.SUPABASE_SERVICE_ROLE_KEY;`. `FORCE ROW LEVEL SECURITY` appears nowhere in the tree. The policies protect the diff, not the data; the only tenancy control that exists at runtime is the `where` clause above, and the admin branch removes it.

**Prescribed invariant, testable as written:**

> For every request, the set of rows returned or written is a subset of the rows whose owning `organizationId` equals the requesting user's `organizationId`. No value of `User.role` widens that set.

**Prescribed enforcement, boring version first (method §1).** Do not start with RLS. The cheap fix is one predicate: `hasCurrentAdminRole` already loads the user row — have it return `{ isAdmin, organizationId }` and make the admin branch `findFirst({ where: { id, organization: { id: orgId } } })` rather than `findUnique({ where: { id } })`, so cross-org access requires a *separate*, audited impersonation path (the repo already has `AdminImpersonation`, per `prisma/schema.prisma:268-269`, and spec §3 lists "audited impersonation" as the Administrator's mechanism — that is the seam this bypass is short-circuiting). Then split `Role.ADMIN` into the org role and a platform capability, because one enum value cannot express both.

**Prescribed rule, so this stops recurring (method §6):** the recurring comment here is "this route forgot the org filter" — replace it with a check, not another review. Add a test/lint rule that fails any `prisma.<tenantModel>.findUnique|findFirst|findMany` reached from `app/api/**` that is not routed through a helper taking the caller's `organizationId`. `assert-tenancy.ts` is already the intended single import; the rule is what makes it unavoidable.

**What would overturn this (method §2):** evidence that `Role.ADMIN` is not reachable by customer self-registration in production — e.g. a Vercel-level gate or a post-signup demotion job I did not find. [UNCONFIRMED] the query that settles it: `SELECT "organizationId", count(*) FROM "User" WHERE role = 'ADMIN' GROUP BY 1 ORDER BY 2 DESC;` — more than one distinct org with an ADMIN means every one of those accounts can read every other org's claims today.

Method-over-instinct, one line: my instinct is to demand `FORCE ROW LEVEL SECURITY` plus a non-owning application role before this ships; method §1 says the untried boring version wins, so the org predicate above is the blocking ask and the DB-enforced version is `DEFERRED` to the condition below.

**DEFERRED condition for DB-side enforcement:** before the first non-Prisma reader of these tables (an anon-key client surface, a BI/analytics connection, or a second service), the app must connect as a non-owning role with `FORCE ROW LEVEL SECURITY` on the tenant tables — at which point the existing policies stop being decorative. [UNCONFIRMED] the one query that tells you where you actually stand: `SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, (SELECT count(*) FROM pg_policies p WHERE p.tablename = c.relname) AS policies FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 2, 3;` plus `SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;` run over the production `DATABASE_URL`.

## signed urls are minted for unverified object paths

Second-order, and independent of the admin bypass: the server will mint a signed URL for any private-bucket path a client can name.

- `signStoredMediaUrl` signs whatever path it parses out of a stored URL, with the service role and no ownership check [VERIFIED] `lib/storage/sign-stored-url.ts:66` — `.createSignedUrl(ref.path, SIGNED_URL_TTL_SECONDS);`.
- The evidence list re-signs both stored URLs on read [VERIFIED] `app/api/inspections/[id]/evidence/route.ts:119` — `fileUrl: await signStoredMediaUrl(e.fileUrl),`.
- On the UNSIGNED create path, `fileUrl` is taken from the request body whenever no server-resolved photo is present [VERIFIED] `app/api/inspections/[id]/evidence/route.ts:275` — `fileUrl: storedPhoto?.url ?? fileUrl ?? null,`; `thumbnailUrl` is client-supplied unconditionally at `:278` and `:431`.
- Paths are org-prefixed [VERIFIED] `lib/storage/supabase-provider.ts:39-40` — ``const prefix = inspectionId`` / ``? `${orgId}/${inspectionId}/${uuid}` ``. The prefix is the only thing that expresses ownership, and nothing compares it to the caller.
- RA-7090 now publishes that exact path in the custody document [VERIFIED] `lib/evidence/manifest-export.ts:298` — `originalStoragePath: evidence.originalStoragePath,`.

Scenario: a technician legitimately downloads a custody export today, which contains `{orgId}/{inspectionId}/{uuid}-original.jpg`. Next month they leave and their `WorkspaceMember.status` flips off `ACTIVE`, so `assertInspectionTenancy` correctly denies them the claim. They then POST a non-photographic evidence item to *their own* new tenant's inspection with `fileUrl` set to that path, GET the list, and receive a fresh one-hour signed URL to the former employer's original photograph — for as long as the object exists. Revoking membership does not revoke the derived capability, because the capability was never bound to the object's owner.

**Prescribed invariant:** a signed URL is only ever minted from a storage path the server itself wrote for that row, and only after the path's org segment is compared to the caller's resolved `organizationId`. Concretely: reject `fileUrl`/`thumbnailUrl` in the evidence POST body when they parse as a private-bucket URL (the canonical photo route is the only writer of those), and have `signStoredMediaUrl` take the caller's org and refuse any path whose first segment differs.

Related, same mechanism, smaller: the custody route resolves the storage provider from the *requester's* org while the path was minted under the *evidence's* org [VERIFIED] `app/api/inspections/[id]/evidence/[evidenceId]/custody/route.ts:222` — `const storage = await getStorageProvider(requester?.organizationId);`. Same-org reads coincide, so this is only observable via the admin branch above or a mirror-provider org — but the fix is the same: resolve provider and authorise from the object's owner, not the reader's.

Credit where due: the manifest verifier itself is the model of how this should be done — `expectedBinding: { inspectionId, capturedByUserId: userId }` re-derives both facts server-side, and `usableKey` narrows a device key to the capturing user rather than trusting the id in the manifest. The gap is that the *bytes* the manifest attests to are addressed by a client-supplied string in a sibling path.

## the tenancy tests bless the bypass

The suite is thorough about stale JWTs and silent about tenants. It asserts the bypass as intended behaviour [VERIFIED] `lib/auth/__tests__/assert-tenancy.test.ts:94` — `it("admin bypass: returns the report regardless of owner", async () => {`, with siblings at `:129` (`"admin path: uses findUnique by id only"`) and `:294` (`"admin: bypasses ownership — id-only scope, no child relation filter"`). Every one of them mocks `prisma`, so no test in the file can observe an organisation at all: a fix that added an org predicate would break these tests, which means the tests currently argue against the fix.

RA-7090's own suites are large (`native-capture-custody.test.ts` 706 lines, `native-capture-e2e.test.ts` 648) and do exercise the negative cases that matter for custody — foreign device key, revoked key, swapped bytes, binding mismatch. What none of them cover is a second organisation.

**Prescribed oracle — one integration test against a real database, two organisations seeded, all five roles including `ADMIN` in org A:**
- Org A `ADMIN` calls the custody route with org B's `inspectionId`/`evidenceId` → expect `404`, and expect **no** `X-Original-Asset-Url` header.
- Same for `GET`/`POST`/`DELETE` on `/api/inspections/[id]/evidence` and the media/sketch routes.
- Positive control first, per the standard that a null result is not evidence: run this test against the current `main` and prove it **fails** (returns 200 today). A cross-tenant test that passes before the fix is testing the mock, not the boundary.
- Add the capability case, not just the object case: a user whose DB role changes from `USER` to a newly added role must not gain claim access by virtue of "not being `USER`".

This is also the missing arm of §39's reference claim — it runs five roles inside one organisation and therefore cannot fail on cross-tenant leakage. The V1 exit gate should seed a **second** organisation whose only purpose is to be invisible.
