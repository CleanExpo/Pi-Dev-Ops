# Ontology + query-expansion method

Turn one industry into a **facet grid** so discovery is systematic, coverage is measurable, and
the diversity check has axes to test against. Ground the vocabulary in prior estate context first
(the `nexus-recall` gate) so facets use the industry's real terms, not invented ones.

## The facet grid — four axes
For the industry, enumerate values on each axis, then take the cross-product as the query set:

- **Subjects** — the entities the industry photographs (people-in-role, equipment, materials,
  outputs, sites). e.g. restoration: technician, moisture meter, air mover, damaged drywall.
- **Scenes** — the settings (on-site, workshop, before/after, close-up detail, wide context).
- **Angles** — the shot framing (hero, over-the-shoulder, top-down, macro, environmental portrait).
- **Conditions** — the variable states (lighting, weather, damage severity, day/night, indoor/out).

A facet is one cell of the grid: `subject × scene × angle × condition` (partial cells are fine —
not every combination is meaningful). Each facet gets ≥1 expanded query.

## Query expansion per facet
For each facet, generate queries that vary vocabulary (synonyms, trade terms), specificity (broad
→ named tool/technique), and source intent (licence-native first: append `site:commons.wikimedia.org`
or an Openverse query for the zero-risk seed pass, then open web).

## Coverage + diversity (feeds §5)
- **Coverage %** — facets with ≥1 accepted (non-quarantined) board image ÷ total meaningful
  facets. Report named gaps (facets with zero coverage).
- **Diversity** — within a facet, flag over-representation (same source domain, near-duplicate
  compositions) and thin axes (a condition or demographic dimension with no references) via
  `diversityFlags` on the records.

Completion criterion: a facet grid exists with per-facet queries; after curation, coverage % and
named gaps are reported and diversity flags are set.
