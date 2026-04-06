// lib/types.ts — shared TypeScript types for Pi CEO platform

export type PhaseStatus = "pending" | "running" | "done" | "error";

export interface Phase {
  id: number;
  name: string;
  skill: string;
  status: PhaseStatus;
  startedAt?: number;
  doneAt?: number;
}

export type TermLineType =
  | "phase"   // orange — phase headers
  | "tool"    // yellow — tool calls
  | "agent"   // text — Claude thinking
  | "success" // green — success
  | "error"   // red — errors
  | "system"  // dim — system info
  | "output"; // text — stdout

export interface TermLine {
  type: TermLineType;
  text: string;
  ts: number;
}

export interface QualityScores {
  completeness: number;
  correctness: number;
  codeQuality: number;
  documentation: number;
}

export interface LeveragePoint {
  id: number;
  name: string;
  score: number; // 1-5
}

export interface AnalysisResult {
  repoUrl: string;
  repoName: string;
  branch: string;
  previewUrl?: string;
  techStack?: string[];
  languages?: Record<string, number>; // lang -> LOC
  totalFiles?: number;
  patterns?: string[];
  quality?: QualityScores;
  zteLevel?: 1 | 2 | 3;
  zteScore?: number;
  leveragePoints?: LeveragePoint[];
  sprints?: Sprint[];
  executiveSummary?: string;
  strengths?: string[];
  weaknesses?: string[];
  nextActions?: string[];
}

export interface Sprint {
  id: number;
  name: string;
  items: SprintItem[];
  duration: string;
}

export interface SprintItem {
  title: string;
  size: "S" | "M" | "L";
  priority: "P1" | "P2" | "P3";
}

export interface Session {
  id: string;
  repoUrl: string;
  repoName: string;
  branch: string;
  startedAt: number;
  completedAt?: number;
  phases: Phase[];
  result?: Partial<AnalysisResult>;
  previewUrl?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  ts: number;
}

export interface SSEEvent {
  type: "line" | "phase_update" | "result_update" | "done" | "error";
  data: TermLine | PhaseUpdate | ResultUpdate | DoneEvent | ErrorEvent;
}

export interface PhaseUpdate {
  phaseId: number;
  status: PhaseStatus;
}

export interface ResultUpdate {
  field: keyof AnalysisResult;
  value: unknown;
}

export interface DoneEvent {
  sessionId: string;
  branch: string;
  previewUrl?: string;
}

export interface ErrorEvent {
  message: string;
}
