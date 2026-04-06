// lib/phases.ts — 8 analysis phase definitions, prompts, and result parsers

import type { Phase, AnalysisResult } from "./types";

export const PHASES: Omit<Phase, "status">[] = [
  { id: 1, name: "CLONE & INVENTORY",   skill: "tier-worker" },
  { id: 2, name: "ARCHITECTURE",        skill: "tier-architect" },
  { id: 3, name: "CODE QUALITY",        skill: "tier-evaluator + agentic-review" },
  { id: 4, name: "CONTEXT",             skill: "context-compressor + big-three" },
  { id: 5, name: "GAP ANALYSIS",        skill: "leverage-audit + zte-maturity" },
  { id: 6, name: "ENHANCEMENT PLAN",    skill: "piter-framework + agent-workflow" },
  { id: 7, name: "EXECUTIVE SUMMARY",   skill: "ceo-mode" },
  { id: 8, name: "COMMIT & PREVIEW",    skill: "agentic-layer" },
];

export const PHASE_PROMPTS: Record<number, string> = {
  1: `PHASE 1 — CLONE & INVENTORY (tier-worker skill)

Analyse the provided repository files. Output ONLY valid JSON:
{
  "totalFiles": <number>,
  "languages": { "<lang>": <loc> },
  "topFiles": ["path1", "path2", ...top 10 by size],
  "frameworks": ["<framework>"],
  "entryPoints": ["<file path>"]
}`,

  2: `PHASE 2 — ARCHITECTURE ANALYSIS (tier-architect skill)

Analyse the architecture. Output valid JSON:
{
  "techStack": ["<tech>"],
  "pattern": "<monolith|microservices|serverless|MVC|other>",
  "entryPoints": ["<path>"],
  "keyDependencies": ["<package>"],
  "dataFlow": "<brief description>",
  "architectureNotes": "<2-3 sentences>"
}`,

  3: `PHASE 3 — CODE QUALITY AUDIT (tier-evaluator + agentic-review skills)

Audit the codebase quality. Review dimensions: Architecture, Naming, Error handling, DRY, Complexity, Conventions.
Output valid JSON:
{
  "scores": {
    "completeness": <1-10>,
    "correctness": <1-10>,
    "codeQuality": <1-10>,
    "documentation": <1-10>
  },
  "issues": [
    { "severity": "high|medium|low", "file": "<path>", "description": "<issue>" }
  ],
  "missingTests": ["<area>"],
  "securityConcerns": ["<concern>"]
}`,

  4: `PHASE 4 — CONTEXT ANALYSIS (context-compressor + big-three skills)

Deeply understand the project. Apply big-three debugging: Model/Prompt/Context.
Output valid JSON:
{
  "projectPurpose": "<1-2 sentences>",
  "targetUsers": ["<user type>"],
  "businessLogic": "<key business rules>",
  "currentState": "<production-ready|alpha|prototype|WIP>",
  "keyInsights": ["<insight>"]
}`,

  5: `PHASE 5 — GAP ANALYSIS (leverage-audit + zte-maturity skills)

Apply the 12 Leverage Points diagnostic and ZTE maturity model.
Score each leverage point 1-5. Calculate ZTE level (12-20: Manual, 21-35: Assisted, 36-48: Autonomous, 49-60: ZTE).
Output valid JSON:
{
  "zteLevel": <1|2|3>,
  "zteScore": <12-60>,
  "leveragePoints": [
    { "id": 1, "name": "Spec Quality", "score": <1-5> },
    { "id": 2, "name": "Context Precision", "score": <1-5> },
    { "id": 3, "name": "Model Selection", "score": <1-5> },
    { "id": 4, "name": "Tool Availability", "score": <1-5> },
    { "id": 5, "name": "Feedback Loops", "score": <1-5> },
    { "id": 6, "name": "Error Recovery", "score": <1-5> },
    { "id": 7, "name": "Session Continuity", "score": <1-5> },
    { "id": 8, "name": "Quality Gating", "score": <1-5> },
    { "id": 9, "name": "Cost Efficiency", "score": <1-5> },
    { "id": 10, "name": "Trigger Automation", "score": <1-5> },
    { "id": 11, "name": "Knowledge Retention", "score": <1-5> },
    { "id": 12, "name": "Workflow Standardization", "score": <1-5> }
  ],
  "productionGaps": ["<gap>"],
  "loadRisks": ["<risk>"]
}`,

  6: `PHASE 6 — ENHANCEMENT PLAN (piter-framework + agent-workflow skills)

Generate a prioritised improvement plan using PITER framework. Group into sprints.
Output valid JSON:
{
  "sprints": [
    {
      "id": 1,
      "name": "<sprint name>",
      "duration": "<Xd>",
      "items": [
        { "title": "<task>", "size": "S|M|L", "priority": "P1|P2|P3" }
      ]
    }
  ],
  "featureList": [
    { "id": "<F001>", "title": "<feature>", "sprint": 1, "status": "planned" }
  ]
}`,

  7: `PHASE 7 — EXECUTIVE SUMMARY (ceo-mode skill)

Write the CEO-level one-page summary. Be direct. No fluff.
Output valid JSON:
{
  "headline": "<one-sentence project description>",
  "currentState": "<paragraph>",
  "strengths": ["<strength>"],
  "weaknesses": ["<weakness>"],
  "risks": ["<risk>"],
  "opportunities": ["<opportunity>"],
  "nextActions": [
    { "action": "<what>", "why": "<why>", "effort": "S|M|L" }
  ]
}`,

  8: `PHASE 8 — COMMIT & PREVIEW

All analysis phases are complete. Summarise what was produced:
Output valid JSON:
{
  "filesCreated": [".harness/spec.md", ".harness/feature_list.json", ".harness/executive-summary.md"],
  "commitMessage": "audit: Pi CEO full analysis — <repo name>",
  "summary": "<2-3 sentences of what was done>"
}`,
};

export function tryParseJson<T>(text: string): T | null {
  try {
    // Extract JSON from markdown code blocks if present
    const match = text.match(/```(?:json)?\s*([\s\S]*?)```/) ?? [null, text];
    return JSON.parse(match[1] ?? text) as T;
  } catch {
    return null;
  }
}

export function applyPhaseResult(
  result: Partial<AnalysisResult>,
  phaseId: number,
  output: string
): Partial<AnalysisResult> {
  const parsed = tryParseJson<Record<string, unknown>>(output);
  if (!parsed) return result;

  switch (phaseId) {
    case 1:
      return {
        ...result,
        totalFiles: parsed.totalFiles as number,
        languages: parsed.languages as Record<string, number>,
      };
    case 2:
      return {
        ...result,
        techStack: parsed.techStack as string[],
        patterns: [parsed.pattern as string],
      };
    case 3:
      return {
        ...result,
        quality: parsed.scores as AnalysisResult["quality"],
      };
    case 5:
      return {
        ...result,
        zteLevel: parsed.zteLevel as 1 | 2 | 3,
        zteScore: parsed.zteScore as number,
        leveragePoints: parsed.leveragePoints as AnalysisResult["leveragePoints"],
      };
    case 6:
      return {
        ...result,
        sprints: parsed.sprints as AnalysisResult["sprints"],
      };
    case 7:
      return {
        ...result,
        executiveSummary: parsed.currentState as string,
        strengths: parsed.strengths as string[],
        weaknesses: parsed.weaknesses as string[],
        nextActions: (parsed.nextActions as Array<{ action: string }>)?.map(
          (a) => a.action
        ),
      };
    default:
      return result;
  }
}
