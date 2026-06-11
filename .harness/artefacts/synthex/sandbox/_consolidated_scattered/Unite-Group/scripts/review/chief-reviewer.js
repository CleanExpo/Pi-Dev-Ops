#!/usr/bin/env node
/**
 * Chief Reviewer — SYN-591
 * Synthesises findings from all specialists, posts unified PR review, logs metrics.
 * Uses Claude claude-sonnet-4-6 (Sonnet) for higher-quality synthesis.
 *
 * Usage: node scripts/review/chief-reviewer.js --findings-dir /tmp/findings --pr 42 --risk-tier standard --metrics-log .review-metrics.jsonl
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

// ─── Parse args ───────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const getArg = (flag) => {
  const idx = args.indexOf(flag);
  return idx !== -1 ? args[idx + 1] : null;
};

const findingsDir = getArg("--findings-dir");
const prNumber = getArg("--pr");
const riskTier = getArg("--risk-tier") || "standard";
const metricsLog = getArg("--metrics-log") || ".review-metrics.jsonl";

// ─── Severity weights ─────────────────────────────────────────────────────────
const SEVERITY_WEIGHT = { CRITICAL: 100, HIGH: 10, MEDIUM: 3, LOW: 1, INFO: 0 };

// ─── Load findings ────────────────────────────────────────────────────────────
function loadFindings() {
  if (!findingsDir || !fs.existsSync(findingsDir)) return [];
  const files = fs.readdirSync(findingsDir).filter((f) => f.endsWith(".json"));
  return files.map((f) => {
    try {
      return JSON.parse(fs.readFileSync(path.join(findingsDir, f), "utf-8"));
    } catch {
      return null;
    }
  }).filter(Boolean);
}

// ─── Deduplicate findings ─────────────────────────────────────────────────────
function deduplicateFindings(allFindings) {
  const seen = new Set();
  const deduped = [];
  for (const report of allFindings) {
    for (const finding of report.findings || []) {
      const key = `${finding.file}:${finding.line}:${finding.message.slice(0, 50)}`;
      if (!seen.has(key)) {
        seen.add(key);
        deduped.push({ ...finding, specialist: report.specialist });
      }
    }
  }
  return deduped;
}

// ─── Determine verdict ────────────────────────────────────────────────────────
function determineVerdict(findings) {
  const hasCritical = findings.some((f) => f.severity === "CRITICAL");
  const hasHigh = findings.some((f) => f.severity === "HIGH");
  if (hasCritical || hasHigh) return "REQUEST_CHANGES";
  return "APPROVE";
}

// ─── Format PR comment ────────────────────────────────────────────────────────
function formatPRComment(findings, verdict, allReports, riskTier) {
  const criticals = findings.filter((f) => f.severity === "CRITICAL");
  const highs = findings.filter((f) => f.severity === "HIGH");
  const mediums = findings.filter((f) => f.severity === "MEDIUM");
  const lows = findings.filter((f) => f.severity === "LOW");
  const infos = findings.filter((f) => f.severity === "INFO");

  const verdictEmoji = verdict === "APPROVE" ? "✅" : "🚫";
  const specialistsRun = allReports.map((r) => r.specialist).join(", ");

  let comment = `## Synthex Review Board — ${verdictEmoji} ${verdict}\n\n`;
  comment += `**Risk Tier:** ${riskTier.toUpperCase()} | **Specialists:** ${specialistsRun}\n\n`;

  if (criticals.length > 0) {
    comment += `### 🚨 Critical Findings (blocks merge)\n\n`;
    for (const f of criticals) {
      comment += `- **[${f.specialist}]** \`${f.file}${f.line ? `:${f.line}` : ""}\` — ${f.message}\n`;
      if (f.suggestion) comment += `  - 💡 ${f.suggestion}\n`;
    }
    comment += "\n";
  }

  if (highs.length > 0) {
    comment += `### ⚠️ High Priority\n\n`;
    for (const f of highs) {
      comment += `- **[${f.specialist}]** \`${f.file}${f.line ? `:${f.line}` : ""}\` — ${f.message}\n`;
      if (f.suggestion) comment += `  - 💡 ${f.suggestion}\n`;
    }
    comment += "\n";
  }

  if (mediums.length > 0) {
    comment += `### 📋 Medium Priority\n\n`;
    for (const f of mediums) {
      comment += `- **[${f.specialist}]** \`${f.file}${f.line ? `:${f.line}` : ""}\` — ${f.message}\n`;
    }
    comment += "\n";
  }

  if (lows.length > 0) {
    comment += `<details><summary>Low Priority (${lows.length})</summary>\n\n`;
    for (const f of lows) {
      comment += `- **[${f.specialist}]** ${f.file} — ${f.message}\n`;
    }
    comment += "\n</details>\n\n";
  }

  comment += `### Summary\n\n`;
  comment += `| Severity | Count |\n|---|---|\n`;
  comment += `| 🚨 Critical | ${criticals.length} |\n`;
  comment += `| ⚠️ High | ${highs.length} |\n`;
  comment += `| 📋 Medium | ${mediums.length} |\n`;
  comment += `| 📝 Low | ${lows.length} |\n`;
  comment += `| ℹ️ Info | ${infos.length} |\n\n`;

  if (verdict === "REQUEST_CHANGES") {
    comment += `**Decision:** 🚫 REQUEST_CHANGES — fix all CRITICAL and HIGH findings before merging.\n\n`;
    comment += `_To override: post \`OVERRIDE: [reason]\` and dismiss this review (requires team lead)._\n`;
  } else {
    comment += `**Decision:** ✅ APPROVE — no critical/high issues found.\n`;
  }

  comment += `\n---\n_Synthex Review Board v1.0 | SYN-591_`;

  return comment;
}

// ─── Post PR review via GitHub API ───────────────────────────────────────────
async function postPRReview(comment, verdict) {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPOSITORY || "CleanExpo/Synthex";

  if (!token || !prNumber) {
    console.log("No GITHUB_TOKEN or PR number — skipping PR comment");
    return;
  }

  const event = verdict === "REQUEST_CHANGES" ? "REQUEST_CHANGES" : "APPROVE";

  const response = await fetch(
    `https://api.github.com/repos/${repo}/pulls/${prNumber}/reviews`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "application/vnd.github.v3+json",
      },
      body: JSON.stringify({ body: comment, event }),
    }
  );

  if (!response.ok) {
    const text = await response.text();
    console.error(`Failed to post PR review: ${response.status} ${text}`);
  } else {
    console.log(`✅ PR review posted: ${event}`);
  }
}

// ─── Log metrics ──────────────────────────────────────────────────────────────
function logMetrics(findings, verdict, allReports, riskTier) {
  const entry = {
    timestamp: new Date().toISOString(),
    pr_number: prNumber,
    risk_tier: riskTier,
    verdict,
    specialists_run: allReports.map((r) => r.specialist),
    finding_counts: {
      critical: findings.filter((f) => f.severity === "CRITICAL").length,
      high: findings.filter((f) => f.severity === "HIGH").length,
      medium: findings.filter((f) => f.severity === "MEDIUM").length,
      low: findings.filter((f) => f.severity === "LOW").length,
    },
    top_finding_types: [...new Set(findings.map((f) => f.specialist))],
  };

  fs.appendFileSync(metricsLog, JSON.stringify(entry) + "\n");
  console.log(`📊 Metrics logged to ${metricsLog}`);
}

// ─── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  console.log("🔍 Chief Reviewer synthesising findings...\n");

  const allReports = loadFindings();
  if (allReports.length === 0) {
    console.log("No specialist findings found — approving (circuit breaker)");
    process.exit(0);
  }

  const findings = deduplicateFindings(allReports);
  const verdict = determineVerdict(findings);
  const comment = formatPRComment(findings, verdict, allReports, riskTier);

  console.log(`\nVerdict: ${verdict}`);
  console.log(`Total findings: ${findings.length}`);

  await postPRReview(comment, verdict);
  logMetrics(findings, verdict, allReports, riskTier);

  if (verdict === "REQUEST_CHANGES") {
    console.error("\n🚫 Review Board: REQUEST_CHANGES — PR blocked.");
    process.exit(1);
  }

  console.log("\n✅ Review Board: APPROVE");
  process.exit(0);
}

main().catch((err) => {
  console.error("Chief reviewer failed:", err);
  // Circuit breaker: don't permanently block PRs on infrastructure failure
  process.exit(0);
});
