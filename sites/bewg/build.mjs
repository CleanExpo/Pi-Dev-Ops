#!/usr/bin/env node
/* Builds the BEWG static site from content/*.json into dist/.
   Run: node sites/bewg/build.mjs   (add --check to validate content only) */
import { readFileSync, writeFileSync, mkdirSync, rmSync, cpSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { home, servicesIndex, servicePage } from './templates/pages.mjs';
import { triagePage, about, contact } from './templates/tools.mjs';

const ROOT = dirname(fileURLToPath(import.meta.url));
const read = (p) => JSON.parse(readFileSync(join(ROOT, p), 'utf8'));

const site = read('content/site.json');
const services = read('content/services.json');
const triage = read('content/triage.json');

/** Fails the build rather than shipping a page with a dead link or empty section. */
function validate() {
  const errors = [];
  const slugs = new Set(services.map((s) => s.slug));
  const required = ['slug', 'title', 'nav', 'short', 'headline', 'intro',
    'signs', 'method', 'deliverables', 'standards', 'related'];

  if (new Set(services.map((s) => s.slug)).size !== services.length) {
    errors.push('duplicate service slug');
  }
  for (const s of services) {
    for (const k of required) {
      if (s[k] === undefined || (Array.isArray(s[k]) && !s[k].length)) {
        errors.push(`${s.slug || '?'}: missing or empty "${k}"`);
      }
    }
    for (const r of s.related || []) {
      if (!slugs.has(r)) errors.push(`${s.slug}: related "${r}" is not a service`);
      if (r === s.slug) errors.push(`${s.slug}: related links to itself`);
    }
    if (!/^[a-z0-9-]+$/.test(s.slug || '')) errors.push(`bad slug: ${s.slug}`);
  }
  for (const q of triage.questions) {
    if (!q.options.length) errors.push(`triage "${q.id}": no options`);
    for (const o of q.options) {
      for (const w of Object.keys(o.weights || {})) {
        if (!slugs.has(w)) errors.push(`triage "${q.id}" → "${o.value}": unknown service "${w}"`);
      }
    }
  }
  for (const k of ['name', 'legalName', 'email', 'phone', 'phoneHref']) {
    if (!site[k]) errors.push(`site.json: missing "${k}"`);
  }
  /* Every service must be reachable from the triage engine, or it is a page
     nobody is ever routed to. */
  const reachable = new Set();
  for (const q of triage.questions) {
    for (const o of q.options) Object.keys(o.weights || {}).forEach((w) => reachable.add(w));
  }
  for (const s of services) {
    if (!reachable.has(s.slug)) errors.push(`${s.slug}: no triage answer routes to this service`);
  }
  return errors;
}

const errors = validate();
if (errors.length) {
  console.error('Content validation failed:');
  errors.forEach((e) => console.error('  - ' + e));
  process.exit(1);
}
console.log(`Content OK: ${services.length} services, ${triage.questions.length} triage questions.`);

if (process.argv.includes('--check')) process.exit(0);

const DIST = join(ROOT, 'dist');
rmSync(DIST, { recursive: true, force: true });
mkdirSync(join(DIST, 'services'), { recursive: true });

const written = [];
const put = (rel, html) => {
  writeFileSync(join(DIST, rel), html);
  written.push(rel);
};

put('index.html', home(site, services));
put('assessment-finder.html', triagePage(site, services, triage));
put('about.html', about(site, services));
put('contact.html', contact(site, services));
put('services/index.html', servicesIndex(site, services));
for (const s of services) put(`services/${s.slug}.html`, servicePage(site, services, s));

cpSync(join(ROOT, 'public'), DIST, { recursive: true });

/* Sitemap and robots, so the service pages can actually be indexed —
   the whole point of splitting them out. */
const urls = written
  .filter((f) => f.endsWith('.html'))
  .map((f) => `${site.baseUrl}/${f.replace(/index\.html$/, '')}`);
put('sitemap.xml',
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
  urls.map((u) => `  <url><loc>${u}</loc></url>`).join('\n') + `\n</urlset>\n`);
put('robots.txt', `User-agent: *\nAllow: /\nSitemap: ${site.baseUrl}/sitemap.xml\n`);

if (!existsSync(join(DIST, 'assets/style.css'))) {
  console.error('Build produced no stylesheet — public/ did not copy.');
  process.exit(1);
}
console.log(`Built ${written.length} files into sites/bewg/dist/`);
written.forEach((f) => console.log('  ' + f));
