// app/api/command-centre/provider-usage/route.ts
//
// GET /api/command-centre/provider-usage — provider usage cockpit. Reads which provider
// keys are PRESENT in the environment and derives quota/usage signals from them.
//
// READ-ONLY, and metadata-only. It never reads a key's value, never reaches
// `credentials_vault`, and holds no write path. `readProviderSignalsFromEnv` inspects
// presence and shape; `buildProviderCockpit` is a pure function over that.
//
// REBUILT, NOT PORTED — for the same reason the wiki-graph route was. The source imports
// `getUser` from its `@/lib/supabase/server`: anon-key, RLS-enforced, per-user. The identical
// specifier resolves in this app to a service-role client with no per-user identity, so a
// verbatim port would have typechecked cleanly while swapping a per-user auth check for
// nothing at all.
//
// Auth: enforced upstream by proxy.ts, which 401s this path without a valid session.
// `/api/command-centre` is in PROTECTED_API_PREFIXES and that is asserted, not assumed, by
// __tests__/command-centre-auth-coverage.test.ts — which fails if the prefix is ever removed.
//
// NOT PORTED alongside this route, both deliberate and recorded:
//   · /api/command-centre/provider-test  — KI-006. Its function is to spend.
//   · /api/command-centre/provider-accounts — KI-007. Credential custody, deferred to
//     per-capability tokens; its repository also carries a production write path.

import { NextResponse } from "next/server";
import {
  buildProviderCockpit,
  readProviderSignalsFromEnv,
} from "@/lib/command-centre/provider-usage";

export const dynamic = "force-dynamic";

// Kept from the source: a metadata-only read must return well under a second, and capping
// the function means a hung cold start fails fast instead of burning the platform maximum.
export const maxDuration = 15;

export async function GET(): Promise<Response> {
  try {
    const signals = readProviderSignalsFromEnv(
      process.env as Record<string, string | undefined>
    );
    const payload = buildProviderCockpit({
      signals,
      now: new Date().toISOString(),
    });
    return NextResponse.json(payload, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (e) {
    // Fixed string only. This handler reads env for PROVIDER KEY PRESENCE, so a raw error
    // message is exactly the wrong thing to hand back — it can name variables and quote
    // values. Log server-side, return nothing useful to a caller.
    console.error("[provider-usage] failed to build cockpit:", e);
    return NextResponse.json(
      { error: "Failed to build provider usage" },
      { status: 500 }
    );
  }
}
