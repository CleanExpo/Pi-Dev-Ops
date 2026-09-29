// Minimal Reticle MCP-over-HTTP client (docs.reticle.sh/http-transport). No global MCP registration needed.
// Library: import { reticleCalls } from './reticle-mcp.mjs'
// CLI:     node reticle-mcp.mjs list
//          node reticle-mcp.mjs '[["reticle_verify",{"action":"change","files":["app/page.tsx"]}]]'
// Tools the server does not advertise are reached through ["reticle_run",{"tool":"<name>","args":{...}}].
import http from 'node:http';
import { pathToFileURL } from 'node:url';

const PORT = Number(process.env.RETICLE_PORT || 4400);

/** Run calls in order over one session. Resolves to [{name, args, text, error}] or rejects on connect failure. */
export function reticleCalls(calls, { timeoutMs = 180000 } = {}) {
  return new Promise((resolve, reject) => {
    let endpoint = null;
    let next = 1;
    const pending = new Map();
    const timer = setTimeout(() => { sse.destroy(); reject(new Error(`reticle: no answer within ${timeoutMs}ms`)); }, timeoutMs);

    const post = (body) => new Promise((ok, fail) => {
      const req = http.request({ port: PORT, path: endpoint, method: 'POST', agent: false, headers: { 'content-type': 'application/json' } },
        (res) => { res.resume(); res.on('end', ok); });
      req.on('error', fail);
      req.end(JSON.stringify(body));
    });
    const rpc = (method, params) => {
      const id = next++;
      return new Promise((ok) => { pending.set(id, ok); post({ jsonrpc: '2.0', id, method, params }).catch(reject); });
    };

    async function run() {
      await rpc('initialize', { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'reticle-verify', version: '1' } });
      await post({ jsonrpc: '2.0', method: 'notifications/initialized' });
      if (calls === 'list') {
        const r = await rpc('tools/list', {});
        return r.result.tools.map((t) => ({ name: t.name, text: t.description || '' }));
      }
      const out = [];
      for (const [name, args] of calls) {
        const r = await rpc('tools/call', { name, arguments: args });
        const text = (r.result?.content || []).map((c) => c.text ?? '').join('\n');
        out.push({ name, args, text, error: r.error ? JSON.stringify(r.error) : undefined });
      }
      return out;
    }

    const sse = http.get({ port: PORT, path: '/mcp/sse', agent: false }, (res) => {
      let buffer = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        buffer += chunk;
        const frames = buffer.split('\n\n');
        buffer = frames.pop();
        for (const frame of frames) {
          const event = /^event: (.*)$/m.exec(frame)?.[1] ?? 'message';
          const data = /^data: (.*)$/m.exec(frame)?.[1] ?? '';
          if (event === 'endpoint') {
            endpoint = data;
            run().then((v) => { clearTimeout(timer); sse.destroy(); resolve(v); }, (e) => { clearTimeout(timer); sse.destroy(); reject(e); });
            continue;
          }
          if (!data) continue;
          let message;
          try { message = JSON.parse(data); } catch { continue; }
          pending.get(message.id)?.(message);
          pending.delete(message.id);
        }
      });
    });
    sse.on('error', (e) => { clearTimeout(timer); reject(new Error(`reticle daemon not reachable on port ${PORT}: ${e.message}`)); });
  });
}

/** Parse a tool's text as JSON, or return undefined. */
export function parseJson(text) {
  try { return JSON.parse(text); } catch { return undefined; }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const arg = process.argv[2];
  const calls = arg === 'list' ? 'list' : JSON.parse(arg || '[]');
  reticleCalls(calls).then((out) => {
    for (const r of out) console.log(`=== ${r.name}${r.args ? ' ' + JSON.stringify(r.args) : ''}\n${r.error || r.text}`);
    process.exit(0);
  }, (e) => { console.error(e.message); process.exit(2); });
}
