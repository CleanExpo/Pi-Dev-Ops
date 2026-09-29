---
name: nexus-scientific
description: "Entry point for 149 vendored scientific research skills (K-Dense). Use for ANY task in bioinformatics and genomics, cheminformatics and drug discovery, proteomics, structural biology, clinical research and medical imaging, materials and computational chemistry, physics, astronomy and quantum, statistics and scientific ML, geospatial science, and the research workflow itself (literature review, experimental design, peer review, grants, writing). Routes to ONE sub-skill; never loads all 149."
license: MIT (upstream K-Dense-AI/scientific-agent-skills)
---

# nexus-scientific

The estate's scientific research library. 149 curated skills covering scientific
libraries, 100+ databases, and research workflows — vendored from
[K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills)
(MIT) and distributed to every machine through the skills-library hub.

This file is a **router**. It is the only thing in the global skill roster; the 149
sub-skills live under `library/` and are checked out on demand, per the Library
doctrine in `~/.claude/CLAUDE.md` §6.

## Routing protocol

1. **Find the skill.** Grep the index — never read it whole:

   ```sh
   grep -i -E 'rna-seq|single.cell' "$HOME/.claude/skills/nexus-scientific/library/INDEX.md"
   ```

   `library/INDEX.md` is a `| dir | what it does |` table over all 149. Match on the
   library name, the database name, the method, or the deliverable.

2. **Check out ONE.** Read `library/<dir>/SKILL.md` and follow it exactly. It may
   point at its own `references/`, `scripts/`, or `examples/` — read those only when
   that skill tells you to.

3. **Check in.** When it has served its purpose, stop re-reading it. Do not
   summarise the sub-skill back to the user; do the work it describes.

**Never** read more than one sub-skill speculatively, and never `cat` `library/`
wholesale — that is 23 MB and will bury the session.

If the grep returns nothing, say so and fall back to normal tool use. A miss is a
real answer; do not force an unrelated skill onto the task.

## Domain quick-map

One hop for the common asks. Anything not listed here → grep `INDEX.md`.

| If the task is about | Start at |
|---|---|
| Single-cell / scRNA-seq | `scanpy`, `anndata`, `scvi-tools`, `scvelo`, `cellxgene-census` |
| Bulk RNA-seq / DE | `bulk-rnaseq`, `pydeseq2`, `pathway-enrichment` |
| Sequences, alignments, variants | `biopython`, `pysam`, `scikit-bio`, `phylogenetics`, `gget` |
| Cheminformatics / molecules | `rdkit`, `datamol`, `molfeat`, `medchem`, `deepchem` |
| Docking, binding, protein structure | `diffdock`, `esm`, `molecular-dynamics`, `torchdrug` |
| Proteomics / mass spec | `pyopenms`, `matchms` |
| Clinical / EHR / trials | `pyhealth`, `clinical-decision-support`, `clinical-reports`, `treatment-plans` |
| Medical imaging / pathology | `pydicom`, `histolab`, `pathml`, `imaging-data-commons` |
| Stats, Bayesian, survival, power | `statsmodels`, `pymc`, `scikit-survival`, `statistical-power`, `statistical-analysis` |
| ML / interpretability / forecasting | `scikit-learn`, `pytorch-lightning`, `shap`, `timesfm-forecasting`, `transformers` |
| Physics, quantum, symbolic maths | `astropy`, `qiskit`, `pennylane`, `qutip`, `sympy`, `fluidsim` |
| Materials / metabolic modelling | `pymatgen`, `cobrapy`, `pymoo`, `simpy` |
| Geospatial | `geopandas`, `geomaster` |
| Big / columnar data | `polars`, `dask`, `vaex`, `zarr-python`, `lamindb` |
| Literature, citations, prior art | `literature-review`, `paper-lookup`, `research-lookup`, `citation-management`, `pyzotero` |
| Hypotheses, critique, peer review | `hypothesis-generation`, `scientific-critical-thinking`, `peer-review`, `scholar-evaluation` |
| Experimental design | `experimental-design`, `statistical-power` |
| Writing, figures, slides, posters | `scientific-writing`, `scientific-visualization`, `matplotlib`, `seaborn`, `scientific-slides`, `latex-posters`, `scientific-schematics` |
| Grants | `research-grants` |
| Documents in / out | `pdf`, `docx`, `xlsx`, `pptx`, `markitdown`, `liteparse` |
| What data/tools exist for X | `get-available-resources`, `database-lookup`, `hugging-science` |

## Estate rules that still bind

The sub-skills are third-party. Estate doctrine wins on conflict:

- **Python runs through `uv`.** Sub-skills quote bare `pip install` / `python x.py`.
  Use `uv run` / `uv pip install` so the environment stays reproducible, per
  [[feedback_full_green_before_handover]]. Never install into system Python.
- **Public-facing words route through `nexus-copywriter`**, then `brand-guardian`.
  A sub-skill writing a paper, abstract, poster, or report does not bypass that gate
  if the output is client- or public-facing.
- **Claims need real sources.** `literature-review` / `paper-lookup` output is
  research substrate, not verified fact — the evidence standard in
  [[feedback_no_false_reporting]] applies. Cite what you actually retrieved.
- **Secrets.** Several sub-skills (`benchling-integration`, `dnanexus-integration`,
  `modal`, `latchbio-integration`, `ginkgo-cloud-lab`, `opentrons-integration`,
  `labarchive-integration`) want API keys. Pull them from 1Password (`op`), never
  hardcode, and check `skills/library/connections.md` first.
- **Credit/compute spend.** Sub-skills that hit paid compute (`modal`,
  `optimize-for-gpu`) or wet-lab / cloud-lab APIs (`adaptyv`, `ginkgo-cloud-lab`,
  `opentrons-integration`, `tamarind`) are real-money or real-world actions. Gate
  them per `autonomy-ladder` — confirm before spending or before anything that moves
  physical lab hardware.

## Provenance and refresh

- Upstream: `K-Dense-AI/scientific-agent-skills`, MIT — see `library/UPSTREAM-LICENSE.md`.
- Pinned commit: `library/UPSTREAM-COMMIT`.
- To pull a newer upstream snapshot:

  ```sh
  sh "$HOME/.claude/skills/nexus-scientific/refresh.sh"
  ```

  It re-vendors `library/`, rewrites `UPSTREAM-COMMIT`, and regenerates `INDEX.md`.
  Review the diff, then commit to skills-library so all machines get it on the next
  `sh ~/.claude/bootstrap.sh`.

Sub-skills are vendored **verbatim**. Do not edit anything under `library/` — a
refresh overwrites it. Estate-specific behaviour belongs in this file.
