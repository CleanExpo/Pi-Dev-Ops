// app/(main)/command-centre/wall/page.tsx — Live Wall kiosk (docs/briefs/live-wall-v1.md).
//
// NEW IN THE TARGET, not ported. Read-only: it polls the session-gated snapshot at
// /api/mesh-fleet/wall and writes nothing. Kiosk URL: /command-centre/wall?machine=<host>&screen=<n>.

import { Suspense } from "react";

import { Wall } from "@/components/wall/Wall";

export const dynamic = "force-dynamic";

export default function WallPage() {
  return (
    <Suspense fallback={null}>
      <Wall />
    </Suspense>
  );
}
