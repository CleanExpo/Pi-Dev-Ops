// app/api/sessions/route.ts — DELETE all sessions (admin clear history)
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase/server";

export async function DELETE(): Promise<NextResponse> {
  try {
    const supabase = createServerClient();
    await supabase.from("sessions").delete().neq("id", ""); // delete all rows
    return NextResponse.json({ cleared: true });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : "Failed" }, { status: 500 });
  }
}
