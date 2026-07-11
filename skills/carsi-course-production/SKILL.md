---
name: carsi-course-production
description: Use whenever creating, editing, refreshing, or reviewing ANY CARSI course, module, lesson, quiz, course trailer, or course marketing copy. Enforces the non-negotiable Australian-production standard (Australian English, 230V/10A power, metric units, Australian-available products, Australian standards/regulators, AUD) and the course quality bar.
---

# carsi-course-production — CARSI courses are Australian-produced (MUST-HAVE)

CARSI is an **Australian** training company (carsi.com.au), operating in the **Australian**
restoration & cleaning market. Every course, module, lesson, quiz, trailer, thumbnail and piece of
course marketing copy is **AUSTRALIAN-PRODUCED**. This is a hard requirement, not a preference —
US/UK data, spelling, power specs, or products are defects and must be corrected before publish.

## The Australian-production checklist (ALL mandatory)

You MUST create a todo for each of these and verify every one before a course is published or an
edit is saved.

### 1. Language — Australian English
- `-ise`/`-isation` (organise, specialise, minimise, optimise, standardise), `-our` (colour, odour,
  behaviour, labour, vapour), `-re` (metre, litre, centre, fibre), doubled-l (labelling, modelling,
  travelling), **mould** (not mold), **licence** (noun)/**license** (verb), **practise** (verb)/
  **practice** (noun), aluminium, tyre, sceptical, enrol/enrolment.
- BANNED US forms: color, odor, behavior, meter (as a length unit — use metre), liter, aluminum,
  mold, fiber, center, defense, "license" as a noun.

### 2. Electrical & power — Australian
- Mains = **230 V nominal, 50 Hz** single-phase (**400 V** three-phase). Standard outlet = **10 A
  GPO** (general power outlet), AS/NZS 3112 plug. Common circuits **10 A / 16 A / 20 A**.
- **Safety switch / RCD**; portable electrical gear is **test-and-tagged** (AS/NZS 3760).
- Redo ALL amp/circuit/power maths at **230 V** (a device is far fewer amps at 230 V than at 115 V).
- BANNED: 110/115/120 V, US "15 A / 20 A circuit" framing, NEMA plugs, "amps @115V".

### 3. Units — metric first
- Metres, millimetres, m², litres, kilograms, °C, kPa/Pa; airflow in **m³/h or L/s** (CFM only as an
  imported spec, with the metric equivalent). Convert imperial source data (e.g. IICRC S500 spacing
  in feet) to **metric primary**, imperial in parentheses.

### 4. Products & equipment — available in Australia, current
- Reference brands/models **actually sold in Australia** through Australian distributors, in
  **240 V/50 Hz** configuration. **State the date** of the availability check (products change).
- Do NOT cite US-only products, US voltages, or US spec sheets as if locally available. Where a US
  brand sells in Australia, use its **Australian distributor + 240 V model + AU pricing**.

### 5. Standards & regulation — Australian
- **AS/NZS** standards; **Safe Work Australia** + state WHS regulators; state **EPA**; **GHS/Safe
  Work Australia** SDS; Poisons Information **13 11 26**; Australian Consumer Law; TGA for any
  therapeutic/disinfection claims. IICRC standards (S500 etc.) ARE used in Australia — cite them, but
  frame within the **Australian regulatory context**, never as US-only.
- AU terminology: GPO, RCD/safety switch, tag-and-test, SWMS, JSEA, site induction, White Card.

### 6. Market context — Australian
- **AUD** pricing (note "inc GST" where relevant), Australian climate/seasons, Australian job types,
  Australian facilities (schools, childcare, aged care, strata), Australian examples and place names.

### 7. E-E-A-T — Australian authority
- Cite Australian bodies and sources; anchor authority to the Australian industry and the founder
  (Phill McGurk). Honour the SEO/GEO/AEO initiative (see memory `carsi-seo-geo-aeo-initiative`).

### 8. IICRC CEC terminology — licence-critical (MUST)
- CARSI is accredited as an **IICRC CEC provider** — NOT accredited to deliver IICRC courses or
  certification. In every course title, description, lesson, quiz and piece of course marketing
  copy, describe what CARSI offers as "IICRC CEC Accredited courses" / "IICRC CEC Accredited" /
  "IICRC Continuing Education Credit (CEC) courses".
- "Accredited" must always be paired with "CEC" (e.g. "IICRC CEC Accredited"). BANNED: bare
  "IICRC Accredited" (drop the CEC qualifier) and "IICRC Course Accredited" / "IICRC-accredited
  course(s)" — both wrongly imply IICRC accredits the course/certification itself rather than
  CARSI's standing as a CEC provider.
- BANNED in any selling/descriptive context: "IICRC courses", "IICRC certification course(s)",
  "IICRC-certified course(s)", "get IICRC certified with CARSI", or any copy implying CARSI
  delivers IICRC certification, examinations, or credentials. IICRC certification is obtained only
  through **IICRC-approved schools and examinations**; CARSI courses earn **CECs** toward
  maintaining an existing IICRC certification.
- **CARSI DESIGNATION RULE (founder 2026-07-10 — MUST).** CARSI issues its OWN credentials, the
  **CARSI Southern Hemisphere Restoration Designations** (e.g. "CARSI Water Restoration Practitioner",
  "CARSI Mould Remediation Practitioner") — like the RIA issuing its own designations, not teaching
  IICRC's. So a CARSI course is **never** branded with an IICRC discipline **acronym**
  (WRT/ASD/AMRT/FSRT/CCT/TCST) and **never** "[discipline]-aligned". Set `iicrcDiscipline: null`;
  put the credential in `meta.designation` + `meta.designationProgram`. Dual value: a CARSI
  designation that **also earns IICRC CECs**.
- FINE: *referencing* a student's own existing IICRC certification (recert reminders, member number,
  CEC tracking), a third-person fact ("FSRT is an IICRC certification covering…"), and citing an
  IICRC S-standard **nominatively** ("ANSI/IICRC S500"). BANNED: using an IICRC discipline acronym or
  "[discipline]-aligned" to name/brand a CARSI course or its trainees.
- Getting this wrong can cost the licence to sell courses — treat as a release blocker. Enforced by
  `npm run check:iicrc-terminology`.

## Course quality bar (applies with the AU standard)
- Real, substantive modules (not stubs); consistent structure; correct `iicrcDiscipline` (or neutral
  for general/knowledge courses); CEC only when genuinely accredited (founder decides value).
- Course-card placeholder is data-driven (see `CourseTextThumbnail`); no ad-hoc stock cover images.
- Trailers are branded Remotion renders **with audio** (voiced via the sanctioned Synthex ElevenLabs
  config, single voice) — a silent trailer is a defect.

## Verification (before publish / before saving an edit)
Scan the content and reject on any hit:
- US spellings (color/odor/meter/mold/fiber/center/license-noun).
- `115V` / `15A circuit` / feet / sq ft / inches without a metric primary.
- US-only products or US voltages presented as locally available.
- IICRC terminology: "IICRC course(s)" / "IICRC certification course" / "IICRC-certified course" /
  "get IICRC certified with CARSI" in selling copy — must be "IICRC CEC course(s)".
- Silent trailer (no audio stream).
Fix all before the course goes live. Prod publish/unpublish remains founder-gated.

## Governance
Prod DB is unreachable locally; course data changes go via the founder's authed admin session (guarded
full-echo PATCH — preserve modules/price/publish/introVideoUrl). `main = prod` (DO deploy_on_push).

## IICRC standards IP + AI use — prohibited (MUST)

Per the IICRC's published AI Use Policy and copyright terms on its official standards store
(iicrc.gilmoreglobal.com), and its brand/trademark enforcement:

- **Never feed IICRC standard text into any AI tooling.** The IICRC prohibits entry of its
  standards and related intellectual property into any form of AI tool, and prohibits creating AI
  derivatives of its published and draft standards. This binds every CARSI content pipeline
  (course-asset-kit, AI course creation, prompt contexts, RAG/embedding corpora) — violation risks
  access suspension and legal action against the licence holder.
- **Never reproduce standard text beyond a brief, attributed reference.** Standards are
  copyright-protected and not printable ("printing limited to small sections for reference only").
  Courses may reference a standard nominatively ("aligned to ANSI/IICRC S500:2021") — never paste
  its sections, tables or procedures. The course-kit excerpt heuristic
  (`src/lib/course-kit/standards-excerpt.ts`, `scanCourseForStandardExcerpts`) flags suspected
  pasted standard text at scaffold time — treat a hit as a release blocker until cleared.
- **Never use IICRC logos or marks without written permission.** The "IICRC" wordmark is
  nominative-use only; logo rights attach to Certified Firms/Registrants under signed agreements,
  and the IICRC publicly enforces violations (its "Invalid Firms" list). CARSI currently uses no
  IICRC mark — keep it that way unless the founder holds written permission.
