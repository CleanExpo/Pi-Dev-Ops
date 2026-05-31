// src/lib/integrations/github/client.ts
import { Octokit } from "@octokit/rest";
import { graphql } from "@octokit/graphql";

const TOKEN = process.env.GITHUB_INTEGRATION_TOKEN ?? "";
if (!TOKEN) console.warn("[github] GITHUB_INTEGRATION_TOKEN not set");

export const octokit = new Octokit({ auth: TOKEN });
export const gql = graphql.defaults({ headers: { authorization: `Bearer ${TOKEN}` } });

export const TRACKED_REPOS: string[] = [
  "CleanExpo/RestoreAssist",
  "CleanExpo/CARSI",
  "CleanExpo/CCW-CRM",
  "CleanExpo/Synthex",
  "CleanExpo/Unite-Group",
  "CleanExpo/Pi-Dev-Ops",
  "CleanExpo/DR-NRPG",
  "CleanExpo/NodeJS-Starter-V1",
];
