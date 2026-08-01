- **file:** `app/(main)/command-centre/wiki-graph/page.tsx`
  **rule exempted:** `auth gate`
  **stated reason:** EXPECTED. getUser()+redirect('/auth/login') removed. The source's per-user auth has no equivalent here - single operator, no identity - and auth is enforced upstream by proxy.ts, whose matcher covers all non-static routes and 401s without a session. The gate moved layer; it was not deleted.

- **file:** `app/(main)/command-centre/wiki-graph/page.tsx`
  **rule exempted:** `database client`
  **stated reason:** EXPECTED. `await createClient()` (anon-key, RLS-enforced) replaced by `createServerClient()` (this app's client). The count rises because the rebuilt call is named differently, not because a second client appeared.
