const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

export { esc };

/** Site header. `depth` is how many directories deep the page sits. */
function head(site, depth) {
  const r = '../'.repeat(depth);
  return `<a class="skip" href="#main">Skip to content</a>
<header class="site-head"><div class="wrap">
  <a class="brand" href="${r}index.html">BEWG<span>${esc(site.legalName)}</span></a>
  <nav class="nav" aria-label="Main">
    <a href="${r}services/index.html">Services</a>
    <a href="${r}assessment-finder.html">Assessment finder</a>
    <a href="${r}about.html">About</a>
    <a href="${r}contact.html">Contact</a>
    <a class="tel" href="tel:${esc(site.phoneHref)}">${esc(site.phone)}</a>
  </nav>
</div></header>`;
}

function foot(site, services, depth) {
  const r = '../'.repeat(depth);
  const links = services
    .map((s) => `<li><a href="${r}services/${s.slug}.html">${esc(s.nav)}</a></li>`)
    .join('');
  return `<footer class="site-foot"><div class="wrap">
  <div class="foot-grid">
    <div>
      <h4>${esc(site.name)}</h4>
      <p>${esc(site.tagline)}<br>${esc(site.coverage)}</p>
    </div>
    <div><h4>Services</h4><ul>${links}</ul></div>
    <div><h4>Start here</h4><ul>
      <li><a href="${r}assessment-finder.html">Find the right assessment</a></li>
      <li><a href="${r}contact.html">Request an assessment</a></li>
      <li><a href="${r}about.html">How we work</a></li>
    </ul></div>
    <div><h4>Contact</h4><ul>
      <li><a href="tel:${esc(site.phoneHref)}">${esc(site.phone)}</a></li>
      <li><a href="mailto:${esc(site.email)}">${esc(site.email)}</a></li>
    </ul><p style="margin-top:12px">${esc(site.lab)}</p></div>
  </div>
  <div class="legal">&copy; ${new Date().getFullYear()} ${esc(site.legalName)}. Independent building science investigation.
  Reports are technical findings on building performance and do not constitute medical or legal advice.</div>
</div></footer>`;
}

/** Contact strip reused across pages. */
export function strip(site, depth) {
  const r = '../'.repeat(depth);
  return `<section class="strip"><div class="wrap">
    <h2>Not sure which assessment you need?</h2>
    <p>Answer six questions and you will get the assessment type that fits, what it involves, and a written brief you can send us.</p>
    <p style="margin:24px 0 22px"><a class="btn" href="${r}assessment-finder.html">Find the right assessment</a></p>
    <a class="big" href="tel:${esc(site.phoneHref)}">${esc(site.phone)}</a>
    <a class="big" href="mailto:${esc(site.email)}">${esc(site.email)}</a>
  </div></section>`;
}

export function page({ site, services, depth = 0, title, description, body, script = '' }) {
  const r = '../'.repeat(depth);
  return `<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<link rel="icon" href="${r}assets/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="${r}assets/style.css">
</head>
<body>
${head(site, depth)}
<main id="main">
${body}
</main>
${foot(site, services, depth)}
${script}
</body>
</html>`;
}
