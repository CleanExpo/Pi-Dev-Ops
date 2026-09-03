import { page, strip, esc } from './layout.mjs';

function questionHtml(q, i) {
  const type = q.multi ? 'checkbox' : 'radio';
  const opts = q.options
    .map(
      (o, j) => `<label class="opt"><input type="${type}" name="${esc(q.id)}" value="${esc(o.value)}"
      data-q="${i}" data-o="${j}"><span>${esc(o.value)}</span></label>`
    )
    .join('');
  return `<fieldset class="q" data-index="${i}">
    <legend>${i + 1}. ${esc(q.label)}</legend>
    ${q.help ? `<p class="help">${esc(q.help)}</p>` : ''}
    <div class="opts">${opts}</div>
  </fieldset>`;
}

export function triagePage(site, services, triage) {
  const qs = triage.questions.map(questionHtml).join('');
  const body = `
<section class="svc-head"><div class="wrap">
  <p class="crumb"><a href="index.html">Home</a> / Assessment finder</p>
  <h1>Which assessment do you actually need?</h1>
  <p class="lede">${esc(triage.intro)}</p>
</div></section>

<section><div class="wrap" style="max-width:900px">
  <div id="form-stage">
    <div class="progress" aria-hidden="true"><i id="bar"></i></div>
    <form id="triage" novalidate>
      ${qs}
      <p id="formErr" class="err" hidden>Answer every question above to see your result.</p>
      <p><button class="btn" type="submit">See my result</button></p>
    </form>
  </div>

  <div id="result-stage" hidden>
    <div class="result">
      <div class="result-head">
        <h2>Your assessment</h2>
        <p>Based on what you described. If it does not match what you expected, call us and talk it through.</p>
      </div>
      <div class="result-body">
        <div id="urgent" class="urgent" hidden></div>
        <div id="recs"></div>
        <h3 style="margin-top:28px">Your details</h3>
        <p class="note">Optional, but a brief with a location and a contact in it can be quoted straight away.
        Nothing is sent anywhere until you press the email button below.</p>
        <div class="grid g2" style="margin-top:16px">
          <div class="field"><label for="c-name">Name</label><input id="c-name" type="text" autocomplete="name"></div>
          <div class="field"><label for="c-phone">Phone</label><input id="c-phone" type="tel" autocomplete="tel"></div>
          <div class="field"><label for="c-email">Email</label><input id="c-email" type="email" autocomplete="email"></div>
          <div class="field"><label for="c-site">Property suburb or address</label><input id="c-site" type="text"></div>
        </div>
        <div class="field"><label for="c-notes">Anything else we should know</label>
        <textarea id="c-notes" rows="3" placeholder="What has already been tried, access constraints, deadlines"></textarea></div>

        <h3 style="margin-top:28px">Your brief</h3>
        <p class="note">A written summary of your answers. Send it to us and we can quote without
        a round of questions first, or keep it for your own records.</p>
        <div class="brief" id="brief"></div>
        <div class="row">
          <a class="btn" id="emailBtn" href="#">Email this to ${esc(site.name)}</a>
          <button class="btn ghost" type="button" id="copyBtn">Copy brief</button>
          <button class="btn ghost" type="button" id="printBtn">Print or save as PDF</button>
          <button class="btn ghost" type="button" id="againBtn">Start again</button>
        </div>
        <p class="note" id="copied" hidden>Copied to your clipboard.</p>
        <p class="note" style="margin-top:20px">Prefer to talk? Call
        <a href="tel:${esc(site.phoneHref)}"><strong>${esc(site.phone)}</strong></a> or email
        <a href="mailto:${esc(site.email)}">${esc(site.email)}</a>.</p>
      </div>
    </div>
  </div>
</div></section>
${strip(site, 0)}`;

  const data = JSON.stringify({
    questions: triage.questions,
    urgency: triage.urgency,
    email: site.email,
    services: services.map((s) => ({
      slug: s.slug, title: s.title, short: s.short, intro: s.intro,
      deliverables: s.deliverables.slice(0, 3),
    })),
  }).replace(/</g, '\\u003c');

  return page({
    site, services, depth: 0, body,
    title: `Assessment finder | ${site.name}`,
    description:
      'Answer six questions about what you are seeing in your building and find out which building science assessment fits, what it involves, and get a written brief to send us.',
    script: `<script id="triage-data" type="application/json">${data}</script>
<script src="assets/triage.js"></script>`,
  });
}

export function about(site, services) {
  const body = `
<section class="svc-head"><div class="wrap">
  <p class="crumb"><a href="index.html">Home</a> / About</p>
  <h1>How we work</h1>
  <p class="lede">${esc(site.tagline)} ${esc(site.coverage)}</p>
</div></section>
<section><div class="wrap"><div class="two"><div>
  <p class="pull">We are hired to answer a question, not to sell the answer's remedy.</p>
  <p class="lede">Building Environmental Wellness Group investigates moisture, condensation, indoor air
  quality and building defect across Australia. The work is diagnostic: establish what is happening inside
  the building, establish why, and set out what the evidence supports doing about it.</p>

  <h2 style="margin-top:44px">Independent of the rectification</h2>
  <p>We do not carry out the remediation we recommend, and we do not take a margin on it. That matters most
  in the cases where the honest finding is that the proposed scope is larger than the evidence supports.</p>

  <h2 style="margin-top:40px">Measurement before opinion</h2>
  <p>Calibrated moisture metering, thermal imaging, psychrometry and pressurisation testing, with reference
  readings from unaffected areas so a number can be interpreted rather than just reported. Where the question
  needs laboratory work, samples go to a NATA-accredited laboratory and the results are interpreted against
  the building conditions we measured, not read out in isolation.</p>

  <h2 style="margin-top:40px">Written for whoever has to act on it</h2>
  <p>A report has to survive being read by a contractor pricing the work, an insurer assessing the claim and,
  sometimes, an expert engaged by the other side. Ours are structured so the evidence chain from observation
  to conclusion is visible, and so the recommended scope can be priced without a further round of questions.</p>

  <h2 style="margin-top:40px">What we do not do</h2>
  <ul class="ticks">
    <li>We do not give medical advice or interpret health outcomes. We report building conditions and
    exposure indicators; clinical questions belong with a medical practitioner.</li>
    <li>We do not certify a building as safe. We report what was measured, where, and under what conditions.</li>
    <li>We do not write a finding to suit the party paying for it.</li>
  </ul>
</div>
<aside class="aside">
  <h3>Coverage</h3><p>${esc(site.coverage)}</p>
  <h3 style="margin-top:20px">Laboratory</h3><p>${esc(site.lab)}</p>
  <h3 style="margin-top:20px">Start here</h3>
  <p style="margin:0 0 16px"><a class="btn" href="assessment-finder.html">Find the right assessment</a></p>
  <p style="margin:0 0 6px"><a href="tel:${esc(site.phoneHref)}"><strong>${esc(site.phone)}</strong></a></p>
  <p><a href="mailto:${esc(site.email)}">${esc(site.email)}</a></p>
</aside></div></div></section>
${strip(site, 0)}`;
  return page({
    site, services, depth: 0, body,
    title: `How we work | ${site.name}`,
    description:
      'Independent building science investigation across Australia. Measurement before opinion, independent of the rectification, reports written to be acted on.',
  });
}

export function contact(site, services) {
  const body = `
<section class="svc-head"><div class="wrap">
  <p class="crumb"><a href="index.html">Home</a> / Contact</p>
  <h1>Request an assessment</h1>
  <p class="lede">Tell us what you are seeing and we will tell you which investigation fits and what it costs.</p>
</div></section>
<section><div class="wrap"><div class="two"><div>
  <h2>The fastest way to get a useful quote</h2>
  <p class="lede">Run the assessment finder first. It takes about a minute, tells you which investigation
  suits your situation, and produces a written brief. Send us that brief and we can price the work without
  a round of back-and-forth questions.</p>
  <p style="margin:26px 0"><a class="btn" href="assessment-finder.html">Find the right assessment</a></p>

  <h2 style="margin-top:40px">Or contact us directly</h2>
  <p style="font-size:21px;margin:0 0 8px"><a href="tel:${esc(site.phoneHref)}"><strong>${esc(site.phone)}</strong></a></p>
  <p style="font-size:19px"><a href="mailto:${esc(site.email)}">${esc(site.email)}</a></p>

  <h2 style="margin-top:40px">What helps us quote accurately</h2>
  <ul class="ticks">
    <li>What you are seeing or smelling, and where in the building</li>
    <li>When it started, and whether it changes with the season or the weather</li>
    <li>Building type, age and number of levels affected</li>
    <li>What has already been done about it, and whether it came back</li>
    <li>What the report is for — insurance, strata, a dispute, or just getting it fixed</li>
    <li>Photographs, if you have them</li>
  </ul>
</div>
<aside class="aside">
  <h3>Coverage</h3><p>${esc(site.coverage)}</p>
  <h3 style="margin-top:20px">Active water?</h3>
  <p>If water is still entering the building, or an occupant is vulnerable, say so when you make contact.
  It changes how quickly we need to attend.</p>
  <h3 style="margin-top:20px">Laboratory</h3><p>${esc(site.lab)}</p>
</aside></div></div></section>`;
  return page({
    site, services, depth: 0, body,
    title: `Request an assessment | ${site.name}`,
    description: `Request a building science assessment. Call ${site.phone} or email ${site.email}.`,
  });
}
