// The truth lines on a Mission Control project card: open PRs, default-branch
// CI, scan age and deploy. Each line is a value, a genuine empty, or
// UNAVAILABLE with the reason. Rendered inside the card button, so spans only.
"use client";

import { useState } from "react";
import { ageLabel, type DeployCheck, type Field, type RepoTruth } from "@/lib/control/card-truth";

const CI_WORDS = { success: "passing", failure: "failing", error: "erroring", pending: "running", expected: "waiting", none: "no checks" } as const;

function fieldLine<T>(label: string, field: Field<T>, render: (value: T) => string): string {
  return field.status === "ok" ? render(field.value) : `${label} UNAVAILABLE: ${field.reason}`;
}

function deployLine(deployments: Record<string, string>, check: DeployCheck | null, nowMs: number): string {
  const urls = Object.values(deployments).filter((url) => typeof url === "string" && url);
  if (urls.length === 0) return "deploy: not tracked";
  if (!check) return `deploy ${urls.join(", ")} · status not recorded`;
  if (check.error) return `deploy UNAVAILABLE: ${check.error}`;
  const age = ageLabel(check.finished_at, nowMs) ?? "date unknown";
  const issues = check.findings.map((finding) => finding.title).join("; ");
  return `deploy ${urls.join(", ")} · ${issues ? `${issues} (${age})` : `responding at last check ${age}`}`;
}

export default function ProjectCardTruth({ truth, finishedAt, deployments, deployCheck, nowMs: fixedNow }: {
  truth: RepoTruth | null;
  finishedAt: string | null | undefined;
  deployments: Record<string, string>;
  deployCheck: DeployCheck | null;
  nowMs?: number;
}) {
  // Ages are measured from first render; the page does not poll, so neither does this.
  const [mountedAt] = useState(() => Date.now());
  const nowMs = fixedNow ?? mountedAt;
  const scanAge = ageLabel(finishedAt, nowMs);
  const lines = [
    truth ? fieldLine("PRs", truth.pull_requests, (v) => `${v.count}${v.capped ? "+" : ""} open PRs`) : "PRs checking…",
    truth ? fieldLine("CI", truth.ci, (v) => `CI ${v.branch}: ${CI_WORDS[v.state]}`) : "CI checking…",
    scanAge ? `scanned ${scanAge}` : "scan date unknown",
    deployLine(deployments, deployCheck, nowMs),
  ];
  return (
    <span data-mc-data="card-truth" style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 11 }}>
      {lines.map((line) => (
        <span key={line} style={line.includes("UNAVAILABLE") ? { color: "#fda4af" } : undefined}>{line}</span>
      ))}
    </span>
  );
}
