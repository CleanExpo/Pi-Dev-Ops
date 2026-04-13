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

You are a senior engineer performing a thorough codebase fingerprint. Analyse every file provided.
Be precise with LOC counts. Detect all frameworks, not just the primary one.
Flag any missing critical files (no README, no tests, no CI config, no .env.example).

Output ONLY valid JSON — no markdown, no commentary:
{
  "totalFiles": <number>,
  "languages": { "<lang>": <loc_count> },
  "topFiles": ["<path — LOC>", ... top 10 largest files],
  "frameworks": ["<name>"],
  "entryPoints": ["<file path>"],
  "testFiles": <number>,
  "testCoveragePresent": <true|false>,
  "ciCdConfig": ["<.github/workflows/*.yml, railway.toml, etc>"],
  "dockerPresent": <true|false>,
  "envExamplePresent": <true|false>,
  "packageManagers": ["<npm|pip|cargo|go.mod|etc>"],
  "totalDependencies": <number>,
  "architecturePattern": "<monolith|microservices|serverless|fullstack|library|cli|other>",
  "missingCriticalFiles": ["<file that should exist but does not>"]
}`,

  2: `PHASE 2 — ARCHITECTURE ANALYSIS (tier-architect skill)

You are a principal architect. Go beyond surface-level tech stack listing.
Map components, their responsibilities, and how data flows between them.
Identify design patterns used (or violated). Call out coupling and cohesion issues.
Security surface: list every external input point and trust boundary.

Output ONLY valid JSON — no markdown, no commentary:
{
  "techStack": ["<technology — version if detectable>"],
  "pattern": "<monolith|microservices|serverless|MVC|event-driven|other>",
  "components": [
    { "name": "<component>", "responsibility": "<single sentence>", "file": "<primary file>" }
  ],
  "entryPoints": ["<path>"],
  "keyDependencies": ["<package — purpose>"],
  "dataFlow": "<clear description of how data moves through the system end-to-end>",
  "externalIntegrations": ["<service — purpose>"],
  "securitySurface": ["<each external input point or trust boundary>"],
  "designPatterns": ["<pattern — where used>"],
  "couplingConcerns": ["<tightly coupled areas that will cause problems>"],
  "architectureNotes": "<3-5 sentences: what works, what is a liability, what will break under load>"
}`,

  3: `PHASE 3 — CODE QUALITY AUDIT (tier-evaluator + agentic-review skills)

You are a skeptical senior engineer performing a production readiness review.
Score honestly — a 7 means genuinely good, not average. A 6 means real problems exist.
Use these explicit rubrics:

COMPLETENESS (1-10):
  10 = All features complete, edge cases handled, nothing stubbed
  8-9 = Core complete, minor edge cases missing
  6-7 = Major features present, some incomplete paths or TODOs
  4-5 = Significant gaps, features that exist but don't fully work
  1-3 = Skeleton or prototype, major functionality missing

CORRECTNESS (1-10):
  10 = No bugs found, all error paths handled, input validated everywhere
  8-9 = Minor issues only, no security holes, rare edge cases may fail
  6-7 = Some unhandled exceptions, missing input validation, potential race conditions
  4-5 = Known bugs, type mismatches, unhandled async errors, security concerns
  1-3 = Fundamental logic errors, crashes under normal use, major security holes

CODE QUALITY (1-10):
  10 = SOLID principles, all functions <40L, all files <300L, no magic numbers, structured logging, full type hints
  8-9 = Mostly clean, minor violations, logging in place, types present
  6-7 = Some functions >80L, some files >400L, print() statements, missing type hints, magic numbers
  4-5 = Many large functions, mixed responsibilities, inconsistent patterns, bare except clauses
  1-3 = Spaghetti code, no structure, hardcoded values throughout, no error handling

DOCUMENTATION (1-10):
  10 = Full README with setup/deploy/arch, docstrings on all public APIs, inline comments on complex logic
  8-9 = Good README, most public APIs documented
  6-7 = README exists but incomplete, sparse docstrings, minimal inline comments
  4-5 = Thin README, undocumented APIs, no inline comments
  1-3 = No documentation, code is not self-explanatory

Output ONLY valid JSON — no markdown, no commentary:
{
  "scores": {
    "completeness": <1-10>,
    "correctness": <1-10>,
    "codeQuality": <1-10>,
    "documentation": <1-10>
  },
  "issues": [
    { "severity": "critical|high|medium|low", "file": "<path>", "line": <number or null>, "description": "<specific issue>" }
  ],
  "missingTests": ["<specific untested area>"],
  "securityConcerns": ["<specific concern with file reference>"],
  "positives": ["<what is genuinely well done>"]
}`,

  4: `PHASE 4 — CONTEXT ANALYSIS (context-compressor + big-three skills)

You are a product strategist and domain expert. Go beyond what the code does — understand WHY it exists,
WHO it serves, and WHAT business rules it encodes. Apply big-three analysis:
  Model: Is the right AI/data model being used for the problem?
  Prompt: Are the prompts/specs structured to get the best output?
  Context: Is the right context being surfaced at the right time?

Assess production readiness honestly:
  production-ready = deployed, stable, handles errors gracefully, monitored
  beta = functional, some rough edges, not fully hardened
  alpha = core working, many gaps, not suitable for real users
  prototype = proof of concept, not production code

Output ONLY valid JSON — no markdown, no commentary:
{
  "projectPurpose": "<1-2 precise sentences: what it does and why it matters>",
  "targetUsers": ["<specific user type with context>"],
  "businessLogic": "<the core rules that make this system work — not just what it does>",
  "currentState": "<production-ready|beta|alpha|prototype>",
  "bigThree": {
    "model": "<assessment of model/algorithm choices — appropriate? better alternatives?>",
    "prompt": "<assessment of how instructions/specs are structured — clear? complete? optimised?>",
    "context": "<assessment of what context is surfaced — relevant? compressed? noise-free?>"
  },
  "keyInsights": ["<non-obvious finding about the codebase that affects decisions>"],
  "deploymentTopology": "<how it runs in production — infra, scaling, dependencies>",
  "dataModels": ["<key data entity and its purpose>"]
}`,

  5: `PHASE 5 — GAP ANALYSIS (leverage-audit + zte-maturity skills)

You are a ZTE maturity assessor. Score each of the 12 leverage points using these explicit criteria.
Be strict — a 5 requires evidence of full implementation, not intent.

SCORING RUBRIC FOR EACH DIMENSION:

1. SPEC QUALITY: Does every feature have a precise, testable acceptance criterion?
   5=full specs with acceptance criteria, context, and edge cases for every feature
   4=most features specified, minor gaps
   3=high-level spec only, no acceptance criteria
   2=vague brief or README
   1=no spec exists

2. CONTEXT PRECISION: Is the right context injected at the right time, compressed and noise-free?
   5=per-intent context compression, lesson injection, relevant examples always present
   4=context provided, some irrelevant content included
   3=basic context, no compression or relevance filtering
   2=minimal context, mostly raw files
   1=no context management

3. MODEL SELECTION: Is the right model chosen for each task tier?
   5=auto-selection by task complexity, cost-optimised routing, fallback logic
   4=deliberate model choice, some routing logic
   3=single model for all tasks
   2=default model, no consideration of alternatives
   1=wrong model for the task

4. TOOL AVAILABILITY: Does the agent have every tool it needs without human intervention?
   5=full tool suite, custom tools for domain needs, MCP servers connected
   4=most tools available, minor gaps
   3=basic tools only (read/write/bash)
   2=limited tools, frequent human unblocking needed
   1=no tools, pure text generation

5. FEEDBACK LOOPS: Does output quality improve automatically over time?
   5=evaluator critique fed back to generator, lessons stored and injected, multi-turn refinement
   4=evaluator exists, feedback stored, partial injection
   3=evaluator exists but feedback not looped back
   2=manual feedback only
   1=no feedback mechanism

6. ERROR RECOVERY: Does the system handle failures without human intervention?
   5=retry with backoff, fallback paths, graceful degradation, error classification
   4=retry logic, most errors handled
   3=basic try/catch, some retries
   2=errors surface to user, no recovery
   1=crashes on any error

7. SESSION CONTINUITY: Can the system resume from exactly where it failed?
   5=phase-level checkpoints, auto-resume, state persisted to disk
   4=session state saved, manual resume possible
   3=session state in memory, lost on crash
   2=must restart from beginning on failure
   1=no session concept

8. QUALITY GATING: Is there a hard gate that blocks bad output from shipping?
   5=automated evaluator gate, minimum score threshold enforced, blocking retry
   4=gate exists, some bypass paths
   3=gate exists but advisory only
   2=human review gate only
   1=no quality gate

9. COST EFFICIENCY: Is the system cost-optimised for its usage pattern?
   5=zero marginal cost architecture, budget tracking, cost per session visible
   4=mostly efficient, some waste
   3=moderate cost, no optimisation
   2=expensive per operation, no tracking
   1=no cost awareness

10. TRIGGER AUTOMATION: Does work start without human initiation?
    5=multiple trigger types (webhook, cron, Linear poller, Telegram), all wired
    4=2-3 trigger types working
    3=1 automated trigger
    2=manual only with automation planned
    1=fully manual

11. KNOWLEDGE RETENTION: Does the system get smarter from every run?
    5=lessons.jsonl fed back, weekly analysis, lesson injection into future runs
    4=lessons stored and sometimes injected
    3=lessons stored but not used
    2=output stored, not analysed
    1=nothing retained

12. WORKFLOW STANDARDIZATION: Is the end-to-end workflow defined, documented, and enforced?
    5=PITER/ADW templates, classifier enforced, all phases defined, no ad-hoc paths
    4=workflow defined, mostly followed
    3=informal workflow, some consistency
    2=ad-hoc, varies by session
    1=no workflow standard

ZTE LEVEL CALCULATION:
  12-20 = L1 MANUAL
  21-35 = L2 ASSISTED
  36-48 = L3 AUTONOMOUS
  49-60 = L4 ZERO TOUCH

Output ONLY valid JSON — no markdown, no commentary:
{
  "zteLevel": <1|2|3|4>,
  "zteScore": <12-60>,
  "leveragePoints": [
    { "id": 1, "name": "Spec Quality", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 2, "name": "Context Precision", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 3, "name": "Model Selection", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 4, "name": "Tool Availability", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 5, "name": "Feedback Loops", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 6, "name": "Error Recovery", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 7, "name": "Session Continuity", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 8, "name": "Quality Gating", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 9, "name": "Cost Efficiency", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 10, "name": "Trigger Automation", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 11, "name": "Knowledge Retention", "score": <1-5>, "evidence": "<what you found>" },
    { "id": 12, "name": "Workflow Standardization", "score": <1-5>, "evidence": "<what you found>" }
  ],
  "productionGaps": ["<specific gap with file/component reference>"],
  "loadRisks": ["<specific risk under load or failure conditions>"],
  "topThreeROI": ["<dimension name — why it has highest ROI to improve>"]
}`,

  6: `PHASE 6 — ENHANCEMENT PLAN (piter-framework + agent-workflow skills)

You are a technical product manager applying the PITER framework:
  P = Problem (what is actually broken or missing)
  I = Impact (business/user consequence of not fixing it)
  T = Task (specific engineering action)
  E = Estimate (S=<1d, M=1-3d, L=3-7d)
  R = Result (measurable outcome after completion)

Group tasks into sprints of 5-7 working days. Sprint 1 = highest-impact fixes first.
P1 = must have (blocking production use), P2 = should have (meaningful improvement), P3 = nice to have.
Do not invent features that were not identified in prior phases. Fix what is broken first.

Output ONLY valid JSON — no markdown, no commentary:
{
  "sprints": [
    {
      "id": 1,
      "name": "<sprint theme>",
      "duration": "<Xd>",
      "goal": "<one sentence: what this sprint achieves>",
      "items": [
        {
          "title": "<specific task — not vague>",
          "size": "S|M|L",
          "priority": "P1|P2|P3",
          "piter": {
            "problem": "<what is broken>",
            "impact": "<consequence of not fixing>",
            "result": "<measurable outcome>"
          }
        }
      ]
    }
  ],
  "featureList": [
    { "id": "F001", "title": "<feature>", "sprint": 1, "status": "planned" }
  ],
  "deferredItems": ["<task that should NOT be prioritised yet and why>"]
}`,

  7: `PHASE 7 — EXECUTIVE SUMMARY (ceo-mode skill)

You are a CEO writing a one-page brief for a board meeting. No fluff. No AI filler words.
Every sentence must answer a specific question. Avoid: robust, seamless, leverage, tapestry, delve, elevate.
Be direct about what is not working. The board already knows the vision — they need the truth.

State clearly:
- What this product actually does (not what it aspires to do)
- What is working in production right now
- What the top 3 risks are that could kill it
- What the next 3 actions are with effort and expected outcome

Output ONLY valid JSON — no markdown, no commentary:
{
  "headline": "<one sentence: what this product does and who uses it>",
  "currentState": "<2-3 sentences: honest assessment of production readiness and active user value>",
  "strengths": ["<specific strength with evidence>"],
  "weaknesses": ["<specific weakness — name the file or component if relevant>"],
  "risks": ["<specific risk — likelihood and consequence>"],
  "opportunities": ["<specific opportunity with estimated impact>"],
  "executiveSummary": "<4-6 sentences: full CEO narrative covering state, momentum, risks, and recommended direction>",
  "nextActions": [
    { "action": "<specific action>", "why": "<business reason>", "effort": "S|M|L", "owner": "human|agent|both" }
  ]
}`,

  8: `PHASE 8 — COMMIT & PREVIEW

All analysis phases are complete. Provide the commit summary.
Output ONLY valid JSON — no markdown, no commentary:
{
  "filesCreated": [".harness/spec.md", ".harness/feature_list.json", ".harness/executive-summary.md"],
  "commitMessage": "audit: Pi CEO full analysis — <repo name>",
  "summary": "<2-3 sentences of what was produced across all 8 phases>"
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
  raw: string,
): Partial<AnalysisResult> {
  const parsed = tryParseJson<Record<string, unknown>>(raw);
  if (!parsed) return result;

  switch (phaseId) {
    case 1:
      return {
        ...result,
        totalFiles:  parsed.totalFiles  as number | undefined,
        languages:   parsed.languages   as Record<string, number> | undefined,
      };
    case 2:
      return {
        ...result,
        techStack: parsed.techStack as string[] | undefined,
      };
    case 3: {
      const scores = parsed.scores as Record<string, number> | undefined;
      return {
        ...result,
        quality: scores ? {
          completeness: scores.completeness ?? 0,
          correctness:  scores.correctness  ?? 0,
          codeQuality:  scores.codeQuality  ?? 0,
          documentation: scores.documentation ?? 0,
        } : result.quality,
      };
    }
    case 4:
      return {
        ...result,
        projectPurpose: parsed.projectPurpose as string | undefined,
        targetUsers:    parsed.targetUsers    as string[] | undefined,
        businessLogic:  parsed.businessLogic  as string | undefined,
        currentState:   parsed.currentState   as string | undefined,
        keyInsights:    parsed.keyInsights    as string[] | undefined,
      };
    case 5: {
      // Validate zteLevel against the actual score bands — never trust Claude's level blindly
      const rawScore = parsed.zteScore as number | undefined;
      const computedLevel: 1 | 2 | 3 | 4 =
        !rawScore       ? 1 :
        rawScore <= 20  ? 1 :
        rawScore <= 35  ? 2 :
        rawScore <= 48  ? 3 : 4;
      return {
        ...result,
        zteLevel:       computedLevel,
        zteScore:       rawScore,
        leveragePoints: parsed.leveragePoints as import("./types").LeveragePoint[] | undefined,
      };
    }
    case 6:
      return {
        ...result,
        sprints: parsed.sprints as import("./types").Sprint[] | undefined,
      };
    case 7:
      return {
        ...result,
        executiveSummary: parsed.executiveSummary as string | undefined,
        strengths:        parsed.strengths        as string[] | undefined,
        weaknesses:       parsed.weaknesses       as string[] | undefined,
        risks:            parsed.risks            as string[] | undefined,
        opportunities:    parsed.opportunities    as string[] | undefined,
        nextActions:      Array.isArray(parsed.nextActions)
          ? (parsed.nextActions as { action?: string; why?: string }[])
              .map((a) => typeof a === "string" ? a : `${a.action ?? ""} — ${a.why ?? ""}`)
          : result.nextActions,
      };
    default:
      return result;
  }
}
