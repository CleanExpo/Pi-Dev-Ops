// Repos registered in config/harness/projects.json.
//
// The dashboard deploys from dashboard/ and cannot read config/harness at run
// time, so this list mirrors the registry. __tests__/registry-repos.test.ts
// fails on any drift: change the registry, then change this list to match.
// Server routes use it to refuse a repo string that is not a registered project.

export const REGISTRY_REPOS: readonly string[] = [
  "CleanExpo/ATO",
  "CleanExpo/CCW-CRM",
  "CleanExpo/DR-NRPG",
  "CleanExpo/DR-Sandbox",
  "CleanExpo/NRPG-Onboarding-Framework",
  "CleanExpo/NodeJS-Starter-V1",
  "CleanExpo/Pi-Dev-Ops",
  "CleanExpo/RestoreAssist",
  "CleanExpo/Synthex",
  "CleanExpo/carsi",
  "CleanExpo/oh-my-codex",
  "CleanExpo/skills-library",
  "CleanExpo/unite-group",
];

/** The registry spelling of `input`, matched case-insensitively; null if not registered. */
export function registryRepo(input: string | null | undefined): string | null {
  if (!input) return null;
  const wanted = input.toLowerCase();
  return REGISTRY_REPOS.find((repo) => repo.toLowerCase() === wanted) ?? null;
}
