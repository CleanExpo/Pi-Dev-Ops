// app/api/capabilities/route.ts — Self-describing API for agentic-layer discovery
export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";

interface Capability {
  name: string;
  description: string;
  method: string;
  path: string;
  inputs?: Record<string, string>;
  outputs?: Record<string, string>;
}

interface CapabilitiesResponse {
  apiVersion: string;
  timestamp: string;
  endpoints: Capability[];
  actions: string[];
  triggerTypes: string[];
  supportedModels: string[];
  metadata: {
    zteLevel: number;
    environment: string;
  };
}

export async function GET(): Promise<NextResponse<CapabilitiesResponse>> {
  const capabilities: CapabilitiesResponse = {
    apiVersion: "1.0.0",
    timestamp: new Date().toISOString(),
    endpoints: [
      {
        name: "Get Capabilities",
        description: "Discover available Pi Dev Ops capabilities",
        method: "GET",
        path: "/api/capabilities",
        outputs: {
          apiVersion: "Semantic version of the API",
          endpoints: "Array of available endpoints",
          actions: "Array of supported action types",
          triggerTypes: "Array of trigger mechanisms",
          supportedModels: "Array of available AI models",
        },
      },
      {
        name: "Analyze Repository",
        description: "Run Pi CEO analysis on a GitHub repository",
        method: "POST",
        path: "/api/analyze",
        inputs: {
          repoUrl: "GitHub repository URL (format: owner/repo or full URL)",
          analysisMode: "Optional: 'cli' or 'api' (defaults to environment setting)",
        },
        outputs: {
          id: "Unique analysis session ID",
          status: "Analysis status (running, completed, failed)",
          result: "AnalysisResult object with findings",
        },
      },
      {
        name: "Generate Actions",
        description: "Generate deliverables from analysis results",
        method: "POST",
        path: "/api/actions",
        inputs: {
          action: "Action type: board_notes | github_issues | dockerfile | cowork_brief",
          result: "AnalysisResult object (partial accepted)",
          repoOwner: "GitHub owner (required for github_issues)",
          repoName: "GitHub repo name (required for github_issues)",
        },
        outputs: {
          output: "Generated content or action result",
        },
      },
      {
        name: "List Sessions",
        description: "Retrieve all analysis sessions",
        method: "GET",
        path: "/api/sessions",
        outputs: {
          sessions: "Array of session objects with analysis history",
        },
      },
      {
        name: "Clear Sessions",
        description: "Admin operation to clear all sessions",
        method: "DELETE",
        path: "/api/sessions",
        outputs: {
          cleared: "Boolean indicating success",
        },
      },
      {
        name: "Retrieve Settings",
        description: "Get current application settings",
        method: "GET",
        path: "/api/settings",
        outputs: {
          settings: "Object containing all settings",
        },
      },
      {
        name: "Chat with Claude",
        description: "Stream chat messages for interactive analysis",
        method: "POST",
        path: "/api/chat",
        inputs: {
          messages: "Array of chat messages with roles and content",
          systemPrompt: "Optional custom system prompt",
        },
        outputs: {
          stream: "ReadableStream of chat responses",
        },
      },
      {
        name: "Smoke Test",
        description: "Run automated regression tests",
        method: "GET",
        path: "/api/cron/analyze",
        outputs: {
          passed: "Number of passed checks",
          failed: "Number of failed checks",
          details: "Array of test results",
        },
      },
    ],
    actions: [
      "board_notes",
      "github_issues",
      "dockerfile",
      "cowork_brief",
    ],
    triggerTypes: [
      "webhook",
      "cron",
      "manual",
    ],
    supportedModels: [
      process.env.ORCHESTRATOR_MODEL || "claude-opus-4-7",
      process.env.ANALYST_MODEL || "claude-sonnet-4-6",
      process.env.WORKER_MODEL || "claude-haiku-4-5-20251001",
      process.env.ANALYSIS_MODEL || "claude-sonnet-4-6",
    ],
    metadata: {
      zteLevel: 3, // Agentic layer satisfied
      environment: process.env.NODE_ENV || "development",
    },
  };

  return NextResponse.json(capabilities);
}
