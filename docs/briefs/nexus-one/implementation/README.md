# Nexus One delivery package

Prepared for Phill McGurk, 8 September 2026.

## Files

- `MASTER_BLUEPRINT.md`: final architectural and operational specification.
- `BUILD_PROMPT.md`: entry instruction for the existing authorised development session.
- `policy.proposal.yaml`: inert configuration proposal; `enabled: false`; not an authority grant.
- `ACCEPTANCE.md`: 50 pilot failure/positive-control cases, UI matrix and outcome metrics.
- `sources.json`: primary documentation references and pinned repository evidence.
- `cockpit-preview.html`: responsive local interaction prototype. All operating data is simulated; no network requests, provider calls or external actions.

Open the HTML file in a browser to inspect the proposed cockpit. Its navigation, filters and evidence panel are local demonstration interactions. The action controls do not operate Mission Control.

The repository main snapshot used in the research is `2c4d346eb8d6723fe48db79c55e34eba1f33f09c`. Re-read current state before implementation. No account, production database, repository branch, PR, deployment, permission or model worker was changed by preparing these files. Independent external-model review remains to be performed through an authorised runtime.

Prototype QA, when present, concerns the local HTML only. It is not proof of the proposed live system.

## Local prototype verification

`PROTOTYPE_QA.json` records 78 passing static/browser checks in Chromium across six viewport sizes, from 320px to 1440px. `prototype_qa.py` reproduces those local checks. The checks include tab navigation, keyboard navigation, filtering, simulated evidence dialogs, a disabled approval control, no browser script errors and no network requests. They do not run the 50 proposed live-system acceptance cases in `ACCEPTANCE.md`, validate Safari/iOS hardware, or certify production accessibility/security.

Desktop, phone and tablet PNGs show the tested prototype. No fonts or external web assets are included.
