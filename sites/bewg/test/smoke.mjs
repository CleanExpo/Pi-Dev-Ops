/* End-to-end smoke test for the BEWG site. Needs playwright:
     npm i -D playwright && node sites/bewg/test/smoke.mjs
   Set CHROMIUM_PATH if chromium lives outside playwright's default cache. */
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFileSync, existsSync, statSync } from 'node:fs';
import { join, extname } from 'node:path';

const DIST = new URL('../dist/', import.meta.url).pathname;
const TYPES = { '.html':'text/html', '.css':'text/css', '.js':'text/javascript',
  '.xml':'application/xml', '.txt':'text/plain', '.svg':'image/svg+xml' };

const server = createServer((req, res) => {
  let p = join(DIST, decodeURIComponent(req.url.split('?')[0]));
  if (existsSync(p) && statSync(p).isDirectory()) p = join(p, 'index.html');
  if (!existsSync(p)) { res.writeHead(404); return res.end('404'); }
  res.writeHead(200, { 'Content-Type': TYPES[extname(p)] || 'application/octet-stream' });
  res.end(readFileSync(p));
});
await new Promise((r) => server.listen(4173, r));

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

const check = (name, ok, extra='') => console.log((ok ? 'PASS  ' : 'FAIL  ') + name + (extra ? ' :: ' + extra : ''));
let failed = 0;
const assert = (name, ok, extra='') => { check(name, ok, extra); if (!ok) failed++; };
const pick = (q, v) => page.check(`input[name="${q}"][value="${v}"]`);

await page.goto('http://localhost:4173/assessment-finder.html');

// 1. submitting empty must not show a result
await page.click('button[type=submit]');
assert('empty submit is blocked', await page.locator('#result-stage').isHidden());
assert('validation message shown', await page.locator('#formErr').isVisible());

// 2. answer a condensation-shaped scenario
await pick('symptoms','Condensation on windows or walls');
await pick('location','Bathroom, laundry or kitchen');
await pick('building','House or townhouse');
await pick('pattern','Worse in winter, better in summer');
await pick('health','No');
await pick('purpose','I just want it diagnosed and fixed');
await page.click('button[type=submit]');
await page.waitForSelector('#result-stage:not([hidden])');

const primary = (await page.locator('.rec.primary h3').textContent()).trim();
assert('condensation scenario routes to condensation service', /Condensation/i.test(primary), primary);

// 3. brief content
const brief = await page.locator('#brief').textContent();
assert('brief names the recommendation', brief.includes('Primary:'));
assert('brief carries the reported answers', brief.includes('Worse in winter'));

// 4. contact fields flow into the brief live
await page.fill('#c-name', 'Test Owner');
await page.fill('#c-site', 'Brunswick VIC');
await page.waitForTimeout(150);
const brief2 = await page.locator('#brief').textContent();
assert('typed contact details update the brief', brief2.includes('Test Owner') && brief2.includes('Brunswick VIC'));

// 5. mailto is populated with the real brief
const mailto = await page.getAttribute('#emailBtn', 'href');
assert('email button targets BEWG', mailto.startsWith('mailto:Consult@bewg.au'));
assert('email body carries the brief', decodeURIComponent(mailto).includes('Test Owner'));

// 6. urgency path
await page.click('#againBtn');
await page.waitForSelector('#form-stage:not([hidden])');
await pick('symptoms','Flood, burst pipe or storm damage');
await pick('location','Across several floors or units');
await pick('building','Commercial or industrial');
await pick('pattern','Suddenly, after a specific event');
await pick('health','Ongoing symptoms, medical advice already sought');
await pick('purpose','An insurance claim');
await page.click('button[type=submit]');
await page.waitForSelector('#result-stage:not([hidden])');
assert('major-loss scenario raises the urgency notice', await page.locator('#urgent').isVisible());
const p2 = (await page.locator('.rec.primary h3').textContent()).trim();
assert('multi-storey flood routes to mapping or major loss', /Moisture Mapping|Major Loss/i.test(p2), p2);

// 7. design-stage scenario
await page.click('#againBtn');
await page.waitForSelector('#form-stage:not([hidden])');
await pick('symptoms','Nothing visible, but something is wrong');
await pick('location','External wall, window or facade');
await pick('building','Under construction or being designed');
await pick('pattern','Not built yet');
await pick('health','No');
await pick('purpose','Design stage compliance or certification');
await page.click('button[type=submit]');
await page.waitForSelector('#result-stage:not([hidden])');
const p3 = (await page.locator('.rec.primary h3').textContent()).trim();
assert('design-stage scenario routes to hygrothermal modelling', /Hygrothermal/i.test(p3), p3);
await page.screenshot({ path: process.env.SHOT_DIR ? process.env.SHOT_DIR + '/result.png' : '/tmp/bewg-result.png', fullPage: false });

// 8. every page renders and has one h1
for (const url of ['/', '/services/', '/services/moisture-mapping.html', '/about.html', '/contact.html']) {
  const r = await page.goto('http://localhost:4173' + url);
  const h1 = await page.locator('h1').count();
  assert('renders ' + url, r.status() === 200 && h1 === 1, `status ${r.status()}, h1 count ${h1}`);
}
await page.goto('http://localhost:4173/');
await page.screenshot({ path: process.env.SHOT_DIR ? process.env.SHOT_DIR + '/home.png' : '/tmp/bewg-home.png', fullPage: false });

// 9. mobile layout does not overflow horizontally
await page.setViewportSize({ width: 390, height: 844 });
await page.goto('http://localhost:4173/services/moisture-mapping.html');
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
assert('no horizontal overflow at 390px', !overflow);

assert('no console errors', errors.length === 0, errors.join(' | '));

await browser.close();
server.close();
console.log(failed ? `\n${failed} CHECK(S) FAILED` : '\nAll checks passed.');
process.exit(failed ? 1 : 0);
