import { page, strip, esc } from './layout.mjs';

const li = (arr) => arr.map((x) => `<li>${esc(x)}</li>`).join('');

export function home(site, services) {
  const cards = services
    .map(
      (s) => `<article class="card">
    <h3>${esc(s.title)}</h3><p>${esc(s.short)}</p>
    <a class="more" href="services/${s.slug}.html">What this involves</a>
  </article>`
    )
    .join('');
  const body = `
<section class="hero"><div class="wrap">
  <h1>The mould is the symptom. We find what is keeping it wet.</h1>
  <p>Independent building science investigation across Australia. Moisture, condensation, indoor air quality
  and building defect — diagnosed with measurement and laboratory analysis, not guesswork.</p>
  <div class="cta-row">
    <a class="btn" href="assessment-finder.html">Find the right assessment</a>
    <a class="btn ghost" href="tel:${esc(site.phoneHref)}">Call ${esc(site.phone)}</a>
  </div>
  <ul class="creds">
    <li>NATA-accredited laboratory analysis</li><li>Australia-wide attendance</li>
    <li>Reports written for insurers, strata and disputes</li>
  </ul>
</div></section>

<section><div class="wrap">
  <p class="eyebrow">The problem with most damp reports</p>
  <h2>A report that names the mould but not the moisture is worth nothing.</h2>
  <p class="lede">Remediation without a documented moisture source fails, usually within a season. Every
  investigation we run starts by establishing the mechanism keeping the building wet — where the water comes
  from, why it stays, and what it will take to stop it. The laboratory work quantifies the consequence. It
  never replaces the diagnosis.</p>
  <div class="grid g3">
    <article class="card"><h3>Measured, not estimated</h3><p>Calibrated metering, thermal imaging and
    psychrometry, with reference readings from unaffected areas so the numbers mean something.</p></article>
    <article class="card"><h3>Independent of the repair</h3><p>We do not quote the rectification we
    recommend. The finding is not shaped by who gets the remediation work.</p></article>
    <article class="card"><h3>Written to be used</h3><p>Scope a contractor can price, evidence an insurer
    can assess, and reasoning that holds up when the other side reads it.</p></article>
  </div>
</div></section>

<section class="tint"><div class="wrap">
  <p class="eyebrow">Services</p>
  <h2>Eight investigations, one discipline.</h2>
  <p class="lede">Every one of them answers the same underlying question: where is the water, why is it
  there, and what does the evidence support doing about it.</p>
  <div class="grid g3">${cards}</div>
</div></section>
${strip(site, 0)}`;
  return page({
    site, services, depth: 0, body,
    title: `Moisture, Mould & Building Science Investigation Australia | ${site.name}`,
    description:
      'Independent building science investigation across Australia. Mould and indoor air quality, moisture mapping, condensation diagnosis, hygrothermal modelling and building defect investigation.',
  });
}

export function servicesIndex(site, services) {
  const cards = services
    .map(
      (s) => `<article class="card">
    <h3>${esc(s.title)}</h3><p>${esc(s.short)}</p>
    <a class="more" href="${s.slug}.html">What this involves</a>
  </article>`
    )
    .join('');
  const body = `
<section class="svc-head"><div class="wrap">
  <p class="crumb"><a href="../index.html">Home</a> / Services</p>
  <h1>Services</h1>
  <p class="lede">Each investigation below sets out what it is for, the signs that point to it, how we carry
  it out and exactly what you receive. If your situation spans more than one, say so — most real problems do.</p>
</div></section>
<section><div class="wrap"><div class="grid g3">${cards}</div></div></section>
${strip(site, 1)}`;
  return page({
    site, services, depth: 1, body,
    title: `Building Science Investigation Services | ${site.name}`,
    description:
      'Mould and IAQ investigation, moisture mapping, condensation diagnosis, hygrothermal modelling, building defect investigation, timber floor moisture, air leakage testing and major loss assessment.',
  });
}

export function servicePage(site, services, s) {
  const related = s.related
    .map((r) => services.find((x) => x.slug === r))
    .filter(Boolean)
    .map((x) => `<li><a href="${x.slug}.html">${esc(x.title)}</a></li>`)
    .join('');
  const body = `
<section class="svc-head"><div class="wrap">
  <p class="crumb"><a href="../index.html">Home</a> / <a href="index.html">Services</a> / ${esc(s.nav)}</p>
  <h1>${esc(s.title)}</h1>
  <p class="lede">${esc(s.short)}</p>
</div></section>

<section><div class="wrap"><div class="two">
  <div>
    <p class="pull">${esc(s.headline)}</p>
    <p class="lede">${esc(s.intro)}</p>

    <h2 style="margin-top:44px">Signs you need this assessment</h2>
    <ul class="ticks">${li(s.signs)}</ul>

    <h2 style="margin-top:44px">How the investigation runs</h2>
    <ol class="steps">${li(s.method)}</ol>

    <h2 style="margin-top:44px">What you receive</h2>
    <ul class="ticks">${li(s.deliverables)}</ul>

    <h2 style="margin-top:44px">Standards and methods applied</h2>
    <ul class="tags">${li(s.standards)}</ul>
  </div>
  <aside class="aside">
    <h3>Is this the right assessment?</h3>
    <p>If you are not certain, the assessment finder takes about a minute and will tell you which
    investigation fits your situation — and produce a brief you can send us.</p>
    <p style="margin:0 0 18px"><a class="btn" href="../assessment-finder.html">Find the right assessment</a></p>
    <h3 style="margin-top:24px">Speak to someone</h3>
    <p style="margin:0 0 6px"><a href="tel:${esc(site.phoneHref)}"><strong>${esc(site.phone)}</strong></a></p>
    <p><a href="mailto:${esc(site.email)}">${esc(site.email)}</a></p>
    ${related ? `<h3 style="margin-top:24px">Often runs alongside</h3><ul class="ticks">${related}</ul>` : ''}
  </aside>
</div></div></section>
${strip(site, 1)}`;
  return page({
    site, services, depth: 1, body,
    title: `${s.title} | ${site.name}`,
    description: s.short,
  });
}
