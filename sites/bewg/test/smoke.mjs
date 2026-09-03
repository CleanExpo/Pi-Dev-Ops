/* End-to-end smoke test for the BEWG site, run against the static export in out/.
     npm run build && node test/smoke.mjs
   Set CHROMIUM_PATH if chromium is outside playwright's default cache. */
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFileSync, existsSync, statSync } from 'node:fs';
import { join, extname, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'out');
const TYPES = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript',
  '.svg': 'image/svg+xml', '.xml': 'application/xml', '.txt': 'text/plain',
  '.woff2': 'font/woff2', '.json': 'application/json', '.ico': 'image/x-icon',
};

const missing = [];
const server = createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  let p = join(OUT, url);
  if (existsSync(p) && statSync(p).isDirectory()) p = join(p, 'index.html');
  else if (!existsSync(p) && existsSync(p + '.html')) p += '.html';
  if (!existsSync(p)) { missing.push(req.url); res.writeHead(404); return res.end('404'); }
  res.writeHead(200, { 'Content-Type': TYPES[extname(p)] || 'application/octet-stream' });
  res.end(readFileSync(p));
});
await new Promise((r) => server.listen(4173, r));
const BASE = 'http://localhost:4173';

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

let failed = 0;
const assert = (name, ok, extra = '') => {
  console.log((ok ? 'PASS  ' : 'FAIL  ') + name + (extra ? ' :: ' + extra : ''));
  if (!ok) failed++;
};
const pick = (q, v) => page.check(`input[name="${q}"][value="${v}"]`);
const shot = (n) => (process.env.SHOT_DIR ? page.screenshot({ path: `${process.env.SHOT_DIR}/${n}.png` }) : null);

await page.goto(`${BASE}/assessment-finder/`);

await page.click('button[type=submit]');
assert('empty submit shows no result', (await page.locator('#result').count()) === 0);
assert('validation message shown', await page.locator('#formErr').isVisible());

await pick('symptoms', 'Condensation on windows or walls');
await pick('location', 'Bathroom, laundry or kitchen');
await pick('building', 'House or townhouse');
await pick('pattern', 'Worse in winter, better in summer');
await pick('health', 'No');
await pick('purpose', 'I just want it diagnosed and fixed');
await page.click('button[type=submit]');
await page.waitForSelector('#result');
const primary = (await page.locator('#result h3').first().textContent()).trim();
assert('condensation scenario routes to condensation', /Condensation/i.test(primary), primary);

const brief = await page.locator('#brief').textContent();
assert('brief names the recommendation', brief.includes('Primary:'));
assert('brief carries reported answers', brief.includes('Worse in winter'));

await page.fill('#c-name', 'Test Owner');
await page.fill('#c-property', 'Brunswick VIC');
await page.waitForTimeout(120);
const brief2 = await page.locator('#brief').textContent();
assert('contact details flow into the brief live',
  brief2.includes('Test Owner') && brief2.includes('Brunswick VIC'));

const mailto = await page.getAttribute('#emailBtn', 'href');
assert('email button targets BEWG', mailto.startsWith('mailto:Consult@bewg.au'));
assert('email body carries the brief', decodeURIComponent(mailto).includes('Test Owner'));
await shot('finder-result');

await page.click('text=Start again');
await page.waitForSelector('#triage');
await pick('symptoms', 'Flood, burst pipe or storm damage');
await pick('location', 'Across several floors or units');
await pick('building', 'Commercial or industrial');
await pick('pattern', 'Suddenly, after a specific event');
await pick('health', 'Ongoing symptoms, medical advice already sought');
await pick('purpose', 'An insurance claim');
await page.click('button[type=submit]');
await page.waitForSelector('#result');
assert('urgency notice raised',
  (await page.locator('text=Mention this when you contact us').count()) > 0);
const p2 = (await page.locator('#result h3').first().textContent()).trim();
assert('multi-storey flood routes to mapping or major loss', /Moisture Mapping|Major Loss/i.test(p2), p2);

await page.click('text=Start again');
await page.waitForSelector('#triage');
await pick('symptoms', 'Nothing visible, but something is wrong');
await pick('location', 'External wall, window or facade');
await pick('building', 'Under construction or being designed');
await pick('pattern', 'Not built yet');
await pick('health', 'No');
await pick('purpose', 'Design stage compliance or certification');
await page.click('button[type=submit]');
await page.waitForSelector('#result');
const p3 = (await page.locator('#result h3').first().textContent()).trim();
assert('design-stage routes to hygrothermal modelling', /Hygrothermal/i.test(p3), p3);

for (const url of ['/', '/services/', '/services/moisture-mapping/', '/about/', '/contact/',
  '/assessment-finder/']) {
  const r = await page.goto(BASE + url);
  const h1 = await page.locator('h1').count();
  assert('renders ' + url, r.status() === 200 && h1 === 1, `status ${r.status()}, h1 ${h1}`);
}

await page.goto(`${BASE}/`);
/* getComputedStyle normalises oklch() to lab() in Chromium, so assert the token
   resolved to a real colour and that it is the brand's, not a browser default. */
const rgbParts = await page.evaluate(() => {
  const probe = document.createElement('div');
  probe.style.color = 'var(--primary)';
  document.body.appendChild(probe);
  const col = getComputedStyle(probe).color;
  probe.remove();
  const c = document.createElement('canvas');
  c.width = c.height = 1;
  const ctx = c.getContext('2d');
  ctx.fillStyle = col;
  ctx.fillRect(0, 0, 1, 1);
  return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3);
});
const brandColour = `rgb(${rgbParts.join(', ')})`;
/* brand primary #12475E -> rgb(18, 71, 94), allowing for oklch round-tripping */
const nearBrand = rgbParts.length >= 3
  && Math.abs(rgbParts[0] - 18) < 12
  && Math.abs(rgbParts[1] - 71) < 12
  && Math.abs(rgbParts[2] - 94) < 12;
assert('brand primary token resolves to BEWG blue', nearBrand, brandColour);
await shot('home');
await page.goto(`${BASE}/services/mould-iaq-investigation/`);
await shot('service');

const sm = await (await page.goto(`${BASE}/sitemap.xml`)).text();
assert('sitemap lists all 8 services', (sm.match(/\/services\/[a-z-]+\//g) || []).length >= 8);

await page.setViewportSize({ width: 390, height: 844 });
for (const url of ['/', '/services/moisture-mapping/', '/assessment-finder/']) {
  await page.goto(BASE + url);
  const over = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert('no horizontal overflow at 390px ' + url, !over);
}

assert('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '));
assert('no missing assets', missing.length === 0, [...new Set(missing)].slice(0, 5).join(' | '));

await browser.close();
server.close();
console.log(failed ? `\n${failed} CHECK(S) FAILED` : '\nAll checks passed.');
process.exit(failed ? 1 : 0);
