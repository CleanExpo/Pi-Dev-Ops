export async function GET() {
  return Response.json({
    status: "ok",
    version: process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0",
    timestamp: new Date().toISOString(),
  });
}
