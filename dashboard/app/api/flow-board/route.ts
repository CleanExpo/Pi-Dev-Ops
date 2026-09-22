import { NextResponse } from "next/server";
import { assembleFlowBoard, emptyFlowBoard, rowFromPull } from "@/lib/control/flowBoard";

export const dynamic = "force-dynamic";

interface GhPull {
  number: number;
  title: string;
  html_url: string;
  created_at: string;
  labels?: Array<{ name: string }>;
}

export async function GET() {
  const token = process.env.GITHUB_TOKEN?.trim();
  if (!token) {
    return NextResponse.json(emptyFlowBoard("GitHub unavailable — GITHUB_TOKEN not set", false));
  }
  try {
    const res = await fetch(
      "https://api.github.com/repos/CleanExpo/Pi-Dev-Ops/pulls?state=open&per_page=30",
      { headers: { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json" }, cache: "no-store" },
    );
    if (!res.ok) {
      return NextResponse.json(emptyFlowBoard(`GitHub unavailable: HTTP ${res.status}`, false));
    }
    const body: unknown = await res.json();
    if (!Array.isArray(body)) {
      return NextResponse.json(emptyFlowBoard("GitHub unavailable: unexpected payload", false));
    }
    const pulls = body as GhPull[];
    const now = Date.now();
    const rows = pulls
      .filter((pull) => (
        Number.isInteger(pull.number)
        && pull.number > 0
        && typeof pull.html_url === "string"
        && typeof pull.created_at === "string"
        && !Number.isNaN(Date.parse(pull.created_at))
      ))
      .map((pull) => rowFromPull({
        id: `PR-${pull.number}`,
        title: typeof pull.title === "string" ? pull.title.slice(0, 160) : "",
        url: pull.html_url,
        paths: [],
        labels: (pull.labels ?? [])
          .map((item) => item.name)
          .filter((name): name is string => typeof name === "string"),
        createdAt: pull.created_at,
        mergedToday: false,
        auditGreen: false,
        nowMs: now,
      }));
    return NextResponse.json(assembleFlowBoard(rows, null));
  } catch {
    return NextResponse.json(emptyFlowBoard("GitHub unavailable", false));
  }
}
