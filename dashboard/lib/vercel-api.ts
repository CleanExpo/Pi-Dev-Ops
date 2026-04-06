// lib/vercel-api.ts — Vercel API: trigger preview deployments for analysis branches

const VERCEL_API = "https://api.vercel.com";

export async function getProjectId(token: string, projectName: string): Promise<string | null> {
  const res = await fetch(`${VERCEL_API}/v9/projects/${projectName}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  const data = await res.json() as { id: string };
  return data.id;
}

export async function createDeployment(
  token: string,
  projectId: string,
  branch: string
): Promise<{ url: string; id: string } | null> {
  const res = await fetch(`${VERCEL_API}/v13/deployments`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name: projectId,
      gitSource: {
        type: "github",
        ref: branch,
      },
      target: "preview",
    }),
  });
  if (!res.ok) return null;
  const data = await res.json() as { url: string; id: string };
  return data;
}

export async function getDeploymentUrl(token: string, deploymentId: string): Promise<string | null> {
  const res = await fetch(`${VERCEL_API}/v13/deployments/${deploymentId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  const data = await res.json() as { url: string };
  return `https://${data.url}`;
}
