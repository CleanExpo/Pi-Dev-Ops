import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PUBLIC_DIR = path.join(__dirname, 'public');
const HARNESS_DIR = path.join(ROOT, '.harness', 'remotion');
const PORT = Number(process.env.REMOTION_WORKSPACE_PORT || 3990);

const PROJECTS = [
  { slug: 'ra', name: 'RestoreAssist', role: 'restoration SaaS product videos + in-app tutorials', repo: '/Users/phillmcgurk/RestoreAssist' },
  { slug: 'dr', name: 'Disaster Recovery', role: 'disaster recovery authority + lead-generation campaigns', repo: '/Users/phillmcgurk/Disaster-Recovery' },
  { slug: 'nrpg', name: 'NRPG', role: 'industry network education + membership campaigns', repo: '/Users/phillmcgurk/NRPG' },
  { slug: 'carsi', name: 'CARSI', role: 'automotive/compliance education + sales enablement', repo: '/Users/phillmcgurk/CARSI' },
  { slug: 'ccw', name: 'CCW', role: 'client campaign lane + product/service marketing', repo: '/Users/phillmcgurk/CCW' },
  { slug: 'synthex', name: 'Synthex', role: 'marketing engine + Synthex voice/media source', repo: '/Users/phillmcgurk/Synthex' },
  { slug: 'unite', name: 'Unite Group', role: 'canonical portfolio/control-plane campaign lane', repo: '/Users/phillmcgurk/Unite-Group' },
] as const;

type EventClient = http.ServerResponse;
const clients = new Set<EventClient>();

function send(event: string, data: unknown): void {
  const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const client of clients) client.write(payload);
}

function json(res: http.ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body, null, 2));
}

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => { body += String(chunk); });
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

function safeJobId(input: string): string {
  return input.toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80) || `job-${Date.now()}`;
}

function serveStatic(req: http.IncomingMessage, res: http.ServerResponse): void {
  const url = new URL(req.url || '/', `http://localhost:${PORT}`);
  const pathname = url.pathname === '/' ? '/index.html' : url.pathname;
  const file = path.normalize(path.join(PUBLIC_DIR, pathname));
  if (!file.startsWith(PUBLIC_DIR)) return json(res, 403, { error: 'forbidden' });
  if (!fs.existsSync(file)) return json(res, 404, { error: 'not found' });
  const ext = path.extname(file);
  const type = ext === '.html' ? 'text/html' : ext === '.js' ? 'text/javascript' : ext === '.css' ? 'text/css' : 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': type });
  fs.createReadStream(file).pipe(res);
}

async function createJob(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
  const payload = JSON.parse(await readBody(req));
  const brief = payload.brief || {};
  const jobId = safeJobId(payload.jobId || `${brief.brand || 'synthex'}-${brief.channel || 'linkedin'}-${Date.now()}`);
  const dryRun = payload.dryRun !== false;
  const outDir = HARNESS_DIR;
  send('progress', { jobId, step: 'queued', message: 'Queued one-shot Remotion dry-run packet' });
  const child = spawn('npx', [
    'tsx',
    'render/one-shot.ts',
    `--brief=${JSON.stringify(brief)}`,
    `--jobId=${jobId}`,
    `--dryRun=${dryRun}`,
    `--outDir=${outDir}`,
  ], { cwd: ROOT, env: process.env });

  child.stdout.on('data', (chunk) => send('progress', { jobId, step: 'stdout', message: String(chunk).trim() }));
  child.stderr.on('data', (chunk) => send('progress', { jobId, step: 'stderr', message: String(chunk).trim() }));
  child.on('close', (code) => {
    const jobDir = path.join(outDir, jobId);
    send('progress', { jobId, step: code === 0 ? 'complete' : 'failed', code, jobDir });
  });
  json(res, 202, { jobId, status: 'started', dryRun, progressUrl: '/events', jobDir: path.join(outDir, jobId) });
}

function listJobs(res: http.ServerResponse): void {
  fs.mkdirSync(HARNESS_DIR, { recursive: true });
  const jobs = fs.readdirSync(HARNESS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => {
      const dir = path.join(HARNESS_DIR, entry.name);
      const packetPath = path.join(dir, 'production-packet.json');
      let packet: Record<string, unknown> | null = null;
      if (fs.existsSync(packetPath)) {
        try {
          packet = JSON.parse(fs.readFileSync(packetPath, 'utf8')) as Record<string, unknown>;
        } catch {
          packet = null;
        }
      }
      const brief = packet?.brief && typeof packet.brief === 'object' ? packet.brief as Record<string, unknown> : {};
      const mp4Path = path.join(ROOT, 'output', `${entry.name}.mp4`);
      return {
        jobId: entry.name,
        dir,
        hasPacket: fs.existsSync(packetPath),
        brand: typeof brief.brand === 'string' ? brief.brand : null,
        channel: typeof brief.channel === 'string' ? brief.channel : null,
        goal: typeof brief.goal === 'string' ? brief.goal : null,
        hasRender: fs.existsSync(mp4Path),
        mp4Path: fs.existsSync(mp4Path) ? mp4Path : null,
        updatedAt: fs.statSync(dir).mtime.toISOString(),
      };
    })
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  json(res, 200, { jobs });
}

function listProjects(res: http.ServerResponse): void {
  fs.mkdirSync(HARNESS_DIR, { recursive: true });
  const jobs = fs.readdirSync(HARNESS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => {
      const packetPath = path.join(HARNESS_DIR, entry.name, 'production-packet.json');
      if (!fs.existsSync(packetPath)) return null;
      try {
        const packet = JSON.parse(fs.readFileSync(packetPath, 'utf8')) as { brief?: { brand?: string } };
        return { jobId: entry.name, brand: packet.brief?.brand || null };
      } catch {
        return null;
      }
    })
    .filter((job): job is { jobId: string; brand: string | null } => Boolean(job));

  const projects = PROJECTS.map((project) => {
    const packetCount = jobs.filter((job) => (
      job.brand === project.slug ||
      job.jobId.startsWith(`${project.slug}-`) ||
      (project.slug === 'ra' && job.jobId.startsWith('ra-'))
    )).length;
    return {
      ...project,
      status: 'connected',
      packetCount,
      commandCentreUrl: `/?brand=${project.slug}`,
    };
  });

  json(res, 200, {
    canonicalControlPlane: 'UNITE_GROUP_*',
    workspace: { port: PORT, dryRunDefault: true, oneVoicePolicy: 'synthex_default_single_voice' },
    projects,
  });
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url || '/', `http://localhost:${PORT}`);
    if (url.pathname === '/events') {
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });
      clients.add(res);
      res.write('event: ready\ndata: {"ok":true}\n\n');
      req.on('close', () => clients.delete(res));
      return;
    }
    if (url.pathname === '/api/jobs' && req.method === 'GET') return listJobs(res);
    if (url.pathname === '/api/jobs' && req.method === 'POST') return createJob(req, res);
    if (url.pathname === '/api/projects' && req.method === 'GET') return listProjects(res);
    serveStatic(req, res);
  } catch (error) {
    json(res, 500, { error: error instanceof Error ? error.message : String(error) });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[remotion-workspace] open http://localhost:${PORT}`);
});
