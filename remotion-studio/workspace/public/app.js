const progress = document.querySelector('#progress');
const jobs = document.querySelector('#jobs');
const form = document.querySelector('#job-form');
const assistButton = document.querySelector('#assist-button');
const assistantPlan = document.querySelector('#assistant-plan');
const projectWiring = document.querySelector('#project-wiring');

let projectMatrix = [];

const brandDefaults = {
  ra: {
    audience: 'restoration business owners, technicians, assessors, and property managers',
    goal: 'show how RestoreAssist turns restoration evidence into a clearer job handover',
    cta: 'Book a RestoreAssist walkthrough',
    brief: 'RestoreAssist keeps inspections, photos, moisture readings, scope, reports, and client handover connected in one restoration-specific workflow.',
    imagePrompt: 'Premium editorial image of a restoration team reviewing moisture mapping and report evidence on a tablet, professional Australian restoration setting, no generic blue-glowing-AI clichés.',
  },
  dr: {
    audience: 'commercial property owners, strata managers, and insurance referrers',
    goal: 'position Disaster Recovery as the fast, trusted response partner after property damage',
    cta: 'Request a disaster recovery response plan',
    brief: 'Disaster Recovery helps property stakeholders move from incident stress to coordinated restoration response with clear evidence, communication, and urgency.',
    imagePrompt: 'Cinematic commercial property restoration response scene, technicians coordinating after water or storm damage, trustworthy and calm, no generic blue-glowing-AI clichés.',
  },
  nrpg: {
    audience: 'restoration practitioners, suppliers, trainers, and industry partners',
    goal: 'explain why restoration professionals should join and contribute to NRPG',
    cta: 'Join the NRPG network',
    brief: 'NRPG brings restoration practitioners together around standards, education, credibility, and industry collaboration.',
    imagePrompt: 'Professional restoration industry roundtable and training environment, Australian practitioners collaborating, editorial documentary style.',
  },
  carsi: {
    audience: 'automotive repairers, assessors, insurers, and compliance teams',
    goal: 'show how CARSI makes automotive repair compliance easier to understand and prove',
    cta: 'Book a CARSI compliance walkthrough',
    brief: 'CARSI helps automotive teams turn technical repair evidence, standards, and compliance steps into a clearer workflow.',
    imagePrompt: 'Premium automotive repair compliance workspace, technicians reviewing repair evidence and compliance documentation, realistic workshop setting.',
  },
  ccw: {
    audience: 'carpet cleaners, restoration contractors, and trade buyers',
    goal: 'promote CCW as the practical supply and support partner for cleaning professionals',
    cta: 'Shop the trade range',
    brief: 'CCW supports cleaning professionals with trade supplies, practical product knowledge, and a clear path to the right equipment.',
    imagePrompt: 'Professional trade supply warehouse for carpet cleaning equipment, warm commercial photography, stocked shelves and working technician.',
  },
  synthex: {
    audience: 'founders and marketing teams',
    goal: 'show how Synthex turns one brief into a shipped marketing video',
    cta: 'Book a strategy call',
    brief: 'Synthex turns marketing ideas into shipped campaigns using agents, Remotion, single-voice narration, and professional production gates.',
    imagePrompt: 'Premium editorial image of an AI marketing command centre, warm cinematic lighting, realistic business context, no generic blue-glowing-AI clichés.',
  },
  unite: {
    audience: 'operators, founders, and portfolio stakeholders',
    goal: 'show Unite Group as the command centre connecting products, operations, and marketing execution',
    cta: 'Review the Unite Group operating model',
    brief: 'Unite Group is the canonical control plane for portfolio execution, coordinating product, marketing, operations, and evidence-backed progress.',
    imagePrompt: 'Dark executive portfolio command centre, multiple product lanes visible, premium operations dashboard style, no generic blue-glowing-AI clichés.',
  },
};

function log(line) {
  const now = new Date().toLocaleTimeString();
  progress.textContent = `${progress.textContent}\n[${now}] ${line}`.trim();
}

function statusLabel(status) {
  if (status === 'connected') return 'connected';
  if (status === 'canonical') return 'canonical Unite-Group';
  if (status === 'local-ready') return 'local workspace ready';
  if (status === 'needs-env-check') return 'verify env';
  return 'pending key/url';
}

function hydrateBrandFields(slug) {
  const defaults = brandDefaults[slug];
  if (!defaults) return;
  form.elements.brand.value = slug;
  form.elements.audience.value = defaults.audience;
  form.elements.goal.value = defaults.goal;
  form.elements.cta.value = defaults.cta;
  form.elements.brief.value = defaults.brief;
  form.elements.imagePrompt.value = defaults.imagePrompt;
  assistantPlan.innerHTML = buildAiPlan(valuesFromForm());
  log(`loaded ${slug} brand defaults into the video brief`);
}

function renderProjectWiring() {
  projectWiring.innerHTML = projectMatrix.map((project) => `
    <article class="wire-row ${project.status}">
      <div>
        <strong>${project.name || project.slug}</strong>
        <small>${project.role}</small>
        <small>${project.repo || ''}</small>
      </div>
      <div class="wire-actions">
        <span>${statusLabel(project.status)} · ${project.packetCount || 0} packets</span>
        <button class="mini" type="button" data-brand="${project.slug}">Use brand</button>
      </div>
    </article>
  `).join('');
  projectWiring.querySelectorAll('[data-brand]').forEach((button) => {
    button.addEventListener('click', () => hydrateBrandFields(button.dataset.brand));
  });
}

function valuesFromForm() {
  const data = new FormData(form);
  const values = Object.fromEntries(data.entries());
  return values;
}

function imageAssetFor(values) {
  if (values.imageProvider === 'none') return [];
  return [{
    sceneId: 'hook',
    path: `assets/generated/${values.brand}-hook-placeholder.png`,
    alt: `${values.brand} generated hero visual`,
    prompt: values.imagePrompt,
    provider: values.imageProvider,
  }];
}

function buildAiPlan(values) {
  const provider = values.imageProvider === 'none' ? 'no generated-image provider' : values.imageProvider;
  const wpm = Math.round((Number(values.durationSec) || 60) * 2.55);
  return `
    <ol>
      <li><strong>Hook:</strong> Lead with one concrete promise for ${values.audience}: ${values.goal}.</li>
      <li><strong>Script timing:</strong> Keep narration below ~${wpm} words for ${values.durationSec}s at a calm single-voice Synthex pace.</li>
      <li><strong>Image direction:</strong> Use ${provider}; generate one hero asset first, then scene-specific replacements after the packet is approved.</li>
      <li><strong>Editing:</strong> Check audio-fit before render; never cut a scene shorter than its voiceover.</li>
      <li><strong>Unite-Group wiring:</strong> Use canonical <code>UNITE_GROUP_API_URL</code> and <code>UNITE_GROUP_API_KEY</code>; treat old Unite-Hub names as legacy aliases only.</li>
    </ol>
  `;
}

async function refreshJobs() {
  const res = await fetch('/api/jobs');
  const data = await res.json();
  jobs.innerHTML = data.jobs.map((job) => `
    <article class="job">
      <strong>${job.jobId}</strong>
      <span>${job.hasRender ? 'render ready' : job.hasPacket ? 'packet ready' : 'pending'}${job.brand ? ` · ${job.brand}` : ''}</span>
      ${job.goal ? `<small>${job.goal}</small>` : ''}
      <small>${job.mp4Path || job.dir}</small>
    </article>
  `).join('') || '<p>No packets yet.</p>';
}

async function refreshProjects() {
  const res = await fetch('/api/projects');
  const data = await res.json();
  projectMatrix = data.projects || [];
  renderProjectWiring();
  log(`connected ${projectMatrix.length} projects to the marketing video command centre`);
}

assistButton.addEventListener('click', () => {
  assistantPlan.innerHTML = buildAiPlan(valuesFromForm());
  log('AI assist generated local storyboard/image/env guidance');
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = valuesFromForm();
  assistantPlan.innerHTML = buildAiPlan(values);
  const brief = {
    brand: values.brand,
    audience: values.audience,
    channel: values.channel,
    durationSec: Number(values.durationSec),
    goal: values.goal,
    cta: values.cta,
    brief: values.brief,
    imageProvider: values.imageProvider,
    imagePrompt: values.imagePrompt,
    imageAssets: imageAssetFor(values),
  };
  const res = await fetch('/api/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brief, dryRun: true }),
  });
  const json = await res.json();
  log(`started ${json.jobId}`);
  await refreshJobs();
});

const events = new EventSource('/events');
events.addEventListener('ready', () => log('connected to localhost:3990 progress stream'));
events.addEventListener('progress', async (event) => {
  const data = JSON.parse(event.data);
  log(`${data.jobId || 'workspace'} · ${data.step}: ${data.message || data.jobDir || ''}`);
  if (data.step === 'complete' || data.step === 'failed') {
    await refreshJobs();
    await refreshProjects();
  }
});

refreshProjects().catch((error) => log(error.message));
refreshJobs().catch((error) => log(error.message));
