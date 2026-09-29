// Render an HTML reference board. ONLY board-eligible, non-quarantined records appear (rights
// gate is enforced here too, defensively). Each tile shows creator, attribution, licence class,
// and an evidence link — provenance travels with every image. Pure string builder.
import { isBoardEligible } from './rights.mjs';

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// records → { html, included, excluded } so the caller can log what the rights gate dropped.
export function renderBoard(records, { title = 'Image reference board' } = {}) {
  const eligible = records.filter(isBoardEligible);
  const excluded = records.length - eligible.length;

  const byFacet = new Map();
  for (const r of eligible) {
    const f = r.facet || '(unfaceted)';
    if (!byFacet.has(f)) byFacet.set(f, []);
    byFacet.get(f).push(r);
  }

  const sections = [...byFacet.entries()].map(([facet, recs]) => {
    const tiles = recs.map((r) => `
      <figure class="tile">
        <img src="${esc(r.canonicalImageUrl)}" alt="${esc(r.taxonomyTags?.join(', '))}" loading="lazy" />
        <figcaption>
          <span class="lic lic-${esc(r.licenceClass)}">${esc(r.licenceClass)}</span>
          <span class="cred">${esc(r.creator || r.sourceAttribution || 'unknown')}</span>
          <a href="${esc(r.licenceEvidenceUrl)}" rel="nofollow noopener">evidence</a>
        </figcaption>
      </figure>`).join('');
    return `<section><h2>${esc(facet)} <small>(${recs.length})</small></h2><div class="grid">${tiles}</div></section>`;
  }).join('\n');

  const html = `<!doctype html><html lang="en-AU"><head><meta charset="utf-8" />
<title>${esc(title)}</title>
<style>
  body{font:14px system-ui,sans-serif;margin:2rem;color:#111;background:#fafafa}
  h1{margin:0 0 .25rem}p.meta{color:#555;margin:0 0 1.5rem}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
  .tile{margin:0;background:#fff;border:1px solid #e2e2e2;border-radius:8px;overflow:hidden}
  .tile img{width:100%;height:160px;object-fit:cover;display:block}
  figcaption{padding:6px 8px;font-size:12px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
  .lic{padding:1px 6px;border-radius:10px;font-size:11px}
  .lic-publicly-reproducible{background:#e6f4ea;color:#137333}
  .lic-nominative-reference-only{background:#fef7e0;color:#8a6d00}
  .lic-licensed-internal{background:#e8f0fe;color:#1a56c4}
  .cred{color:#444}a{color:#1a56c4;margin-left:auto}
</style></head><body>
<h1>${esc(title)}</h1>
<p class="meta">${eligible.length} reference image(s) · ${excluded} excluded by the rights gate · references only, not for republication</p>
${sections}
</body></html>`;

  return { html, included: eligible.length, excluded };
}
