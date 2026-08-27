import { piCeoFetch } from "@/lib/pi-ceo-session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  try {
    const res = await piCeoFetch("/api/model-fabric/status", {}, 5_000);
    if (!res) {
      return Response.json(
        { enabled: false, healthy: false, error: "Pi-CEO unavailable" },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    return Response.json(
      {
        enabled: false,
        healthy: false,
        error: error instanceof Error ? error.message : "Model Fabric status failed",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
