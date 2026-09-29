# Plan: <feature name>

> Derives from `spec.md` — every section here maps to a requirement there; cite it (R#).

## Tech decisions
| Decision | Choice | Rationale (cite constitution rule / spec R# / research) |
|---|---|---|

## Architecture touch-points
Every file/module to be created or modified, each `[VERIFIED]` by reading it first:

| File | Change | Serves R# | Evidence |
|---|---|---|---|

## Data model deltas
Schema/migration changes (additive preferred; destructive needs the human).
State the migration-safety story (two-step renames, no locking index builds, rollback).

## API contracts
New/changed endpoints: method, path, auth, request/response shape, error codes.
Follow the repo's response idiom; note rate-limit + validation per endpoint.

## Rollout & reversibility
Feature flag? Env var? Migration order vs deploy order? How to roll back in one step.

## Explicitly rejected (over-engineering guard)
What we are NOT building even though it was tempting, and why the spec doesn't need it.

## Research notes
Findings that drove decisions (versions, provider limits, prior art in the repo), cited.
