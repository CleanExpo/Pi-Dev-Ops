# Truth, Research & Deliver (TRD) v1.0

**Reusable skill + working Python verification gate for Claude, JEV, Codex and Mission Control.** Australian English. Python 3.10+ and standard library only. Includes independent reviewer prompts, installation, retrospective audit queues, release statuses and adversarial tests.

> **TRD is not an AI lie detector.** It enforces traceable source-to-claim evidence, independent review, auditability and fail-closed publishing controls. Its initial source-origin check is an independently supplied attestation and fingerprint, *not* live identity verification of a publisher. AI consensus does not prove truth.

## What's included

- `SKILL.md` - reusable shared agent contract.
- `spec.md` - complete system architecture, controls and phase-2 engineering backlog.
- `trd/core.py` - deterministic fingerprint, excerpt, provenance, arithmetic, source-lineage, review and release checks.
- `trd/cli.py` - `init`, `inventory`, `backfill`, `packets`, `sign-review`, `gate`.
- `agents/CLAUDE_REVIEW.md` and `agents/JEV_REVIEW.md` - separate blinded review assignments.
- `install.py` - explicit, idempotent per-project installer for Claude and Codex skill locations.
- `integration/MISSION_CONTROL.md` - scheduling, stage gates, tasks, backfill and three-machine design.
- `integration/CI_EXAMPLE.yml` - proposed protected publish-time gate.
- `docs/SCHEMA.md` and `docs/THREAT_MODEL.md` - claim/reviewer format and controls.
- `tests/` - automated tamper, contradiction, arithmetic and independence tests.
- `examples/` - synthetic demo that must NOT be mistaken for verified real-world evidence.

## Quick start: Audit a single project

**1. Download/extract this package.** Run in the extracted folder:

```bash
python -m unittest discover -s tests -v
python install.py --root /absolute/path/to/your/project
```

The installer writes only inside the selected project. It creates `.trd/` tooling, `.agents/skills/trd-truth-research-deliver/SKILL.md`, `.claude/skills/trd-truth-research-deliver/SKILL.md`, and appends an idempotent TRD reference to that repo's `AGENTS.md` and `CLAUDE.md`.

**2. Run inside the project root after installation.**

macOS/Linux:
```bash
PYTHONPATH=.trd/tooling python3 -m trd inventory .
PYTHONPATH=.trd/tooling python3 -m trd backfill .
```

Windows PowerShell:
```powershell
$env:PYTHONPATH = ".trd\tooling"
python -m trd inventory .
python -m trd backfill .
```

These commands produce `.trd/legacy/inventory.json` and `.trd/legacy/candidate_queue.json`. All entries start `UNREVIEWED` / `UNVERIFIED` and need original sources and external reviews before promotion.

**3. Register every material claim** using `docs/SCHEMA.md` (include an actual report hash, source snapshots, origin check proofs and exact source excerpts). Do not invent data to complete the record.

**4. Generate separate review packets** (within the installed repo):

```bash
PYTHONPATH=.trd/tooling python3 -m trd packets .trd/cases/CASE-001.json \
  --root . --out .trd/reviews/CASE-001/packets
```

Run Claude and JEV on the independent packets in separate authorised agents/runners. Their verdict files must be for the *identical frozen case*; they must not see each other's review. Packets alone do not invoke agents.

**5. Trusted runner signs each genuine review.** The signing secret for each reviewer must be present **only inside that runner**, never exposed to model tools or writing agents:

```bash
# The trusted Claude runner, and separately the trusted JEV runner:
python -m trd sign-review unsigned-claude.json --out Claude.json
# with its own isolated TRD_CLAUDE_REVIEW_KEY of >=32 characters
```

For the JEV service use `TRD_JEV_REVIEW_KEY`. Reviewer content must be independently validated by its trusted service before signing. The signer command *does not itself prove an AI run occurred*; trustworthy control of this step is your infrastructure's responsibility.

**6. Enforce the release gate on the final output:**

```bash
PYTHONPATH=.trd/tooling python3 -m trd gate .trd/cases/CASE-001.json \
  --root . --reviews .trd/reviews/CASE-001/signed \
  --out .trd/results/CASE-001.json
```

- Exit code `0` / **PASS**: evidence process passed. Existing human/professional approvals remain necessary when relevant.
- Exit code `2` / **HOLD**: missing, stale, or incomplete verification. Must not present as verified.
- Exit code `3` / **BLOCK**: contradiction, forgery/tamper, wrong arithmetic, or other hard failure. Repair first.

Release only after PASS **at the actual export/publish boundary**. If the output or case changes, reviews must be repeated, and the artifact hash updated.

## The immediate production limitation
The provided system has been built and unit-tested in this package; **it has not been installed in your machines or GitHub repos and has not executed Claude/JEV reviews of your real project files**. Production rollout requires access to the correct project root, your true JEV/Claude runner interface, a real origin-checking service, isolated trusted signing identities and a protected publishing gate. Do not consider it a finished, live, end-to-end deployment merely because the skill is installed.

## How to use across all projects
Start by installing into one pilot repository, run tests, backfill and trace one real report end-to-end. Then place the verifier in a separate pinned protected distribution (recommended) and roll the skill/hook to your other projects. Use `integration/MISSION_CONTROL.md` for orchestration. Repositories can consume a single approved version; avoid copy/paste drift. Each project should have independent evidence cases and access controls, sharing only source references that are legally and technically reusable.

## Test command
```
python -m unittest discover -s tests -v
```

The passing fixture in tests is **synthetic** and must not be used as scientific, legal, technical or restoration evidence.

## Standards used in the architecture
- NIST AI RMF Generative AI Profile: https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- W3C PROV-O: https://www.w3.org/TR/prov-o/
- Crossref REST API: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- C2PA: https://spec.c2pa.org/specifications/specifications/2.5/specs/C2PA_Specification.html

## Batch rollout to many repositories

List discovered Git projects **without changing anything**:
```bash
python install_all.py --repos-root "/path/to/repository-parent"
```

Then install into the discovered projects explicitly:
```bash
python install_all.py --repos-root "/path/to/repository-parent" --apply
```

The installer skips already installed copies. For reviewed upgrades, add `--upgrade` to back up the old gate before overwriting it. The scanner ignores non-repository folders and does not deploy or merge code.
