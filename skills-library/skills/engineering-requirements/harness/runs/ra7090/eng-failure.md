by: eng-failure
contributed: [eng-failure]
categories:
  failure_modes: {state: PRESCRIBED, ref: "#two-step-capture-write-with-no-timeout-and-no-compensation", by: eng-failure, blocking: true}
  invariants:    {state: PRESCRIBED, ref: "#unsigned-evidence-has-no-custody-event-and-no-durable-replay-identity", by: eng-failure, blocking: true}
  observability: {state: PRESCRIBED, ref: "#nothing-counts-a-fleet-that-stopped-signing", by: eng-failure}
cross_domain:
  - "the new migrations run CREATE UNIQUE INDEX (non-concurrent) and ADD CONSTRAINT FOREIGN KEY with no lock_timeout, taking ACCESS EXCLUSIVE on EvidenceItem and InspectionPhoto during deploy — eng-data owns whether current row counts make that a real stall"
  - "the two-step down.sql staging (drop index/FK now, drop columns in a later release) reads correct; eng-rollback owns confirming step 2 is actually scheduled rather than forgotten"
  - "extractAndSaveMediaAsset defers work via setImmediate after the response returns, which a frozen serverless instance may never run — eng-observability owns whether MediaAsset writes are silently not happening"
  - "the §39 seeded reference claim lists photographs but no device-signed capture and no custody-chain assertion, so the exit gate cannot detect either finding below — eng-test owns"
  - "my instinct was to block on the migration lock; METHOD.md §5 says quality claims get numbers and I have no prod row count, so it goes here instead of in my section"

## Two-step capture write with no timeout and no compensation

`uploadNativeCapture` is a distributed transaction across two HTTP endpoints with no timeout on either leg, no compensation for a half-completed run, and no durable record of the bytes it is carrying.

**[VERIFIED]** `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/lib/evidence/native-capture-upload.ts:94` — `const photoRes = await fetchImpl(` … no `signal`, no `AbortSignal.timeout`; same at `:166` for the evidence leg. `grep -n "AbortController\|AbortSignal\|timeout"` over `native-capture-upload.ts`, `device-signing.ts`, `ios-capture.ts`, `roomplan-capture.ts` returns nothing.

**Scenario A — the orphan.** Step 1 succeeds (`InspectionPhoto` row + private original bytes + `cocoaSha256` + `AuditLog`), step 2 throws at `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/lib/evidence/native-capture-upload.ts:188` — `if (!evidenceRes.ok) {` — because the WKWebView dropped the second request, the session cookie expired between legs, or the route 500'd. The photo is now in the gallery and in storage with a server-recomputed custody digest, and no `EvidenceItem` references it. Nothing sweeps it, nothing counts it, and the workflow step still reads "not captured". `grep -rn "orphan"` across `lib` and `app` returns no photo/evidence reconciliation path.

**Scenario B — one hung request kills the whole capture surface.** `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/app/dashboard/inspections/[id]/capture/page.tsx:230` — `const [uploadingEvidence, setUploadingEvidence] = useState(false);` — is a single page-level boolean, and `:1011` — `disabled={uploadingEvidence}` — is on *every* required-evidence capture button. One 20 MB multipart stalling on a half-bar of LTE in a wet building disables every other capture on that step, with a spinner and no cancel, for as long as the webview is willing to wait. That is a pool of size one with an infinite timeout.

**Scenario C — the failure this feature exists for destroys the evidence.** `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/lib/evidence/ios-capture.ts:53` — `const blob = await (await fetch(dataUrl)).blob();` — the captured bytes live only in memory. On a network failure the throw propagates to `:425` of the capture page, `toast.error(msg)` fires, and the blob is garbage. The technician must re-shoot — after the ceiling has been stripped, or from the van park. There is no queue to fall back on: `grep -rn "inspection-store"` across `app lib components` returns exactly one non-test importer, `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/app/dashboard/inspections/[id]/capture/page.tsx:69` — `import { getQueuedDraftCount } from "@/lib/offline/inspection-store";` — and that module stores inspection *form drafts*, not captures. The module's own header at `native-capture-upload.ts:22` reasons about "an offline queue replaying the same capture"; that queue does not exist in this repo, so the exactly-once design is defending a path nothing can reach while the lossy path is unguarded.

**[VERIFIED]** the spec already requires the missing piece — `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/spec.md:278`:

> Offline-first field capture with durable mutation queue, per-mutation idempotency keys, stale-processing recovery, and version-preconditioned replay so an offline device cannot silently clobber concurrent edits (fixes RA-ARCH-02 M6).

**Scenario D — a batch tells you the wrong file failed.** **[VERIFIED]** `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/app/api/inspections/[id]/evidence/batch/route.ts:289-294`:

> ```ts
>     const dbFailures = createdItems
>       .filter((r) => r.status === "rejected")
>       .map((_, idx) => ({
>         filename: uploadedItems[idx]?.item.input.filename ?? "unknown",
> 
`idx` indexes the *filtered* array. Upload six files, have the sixth `create` reject, and the response reports `photo-1.jpg` as failed — a file that is also in `succeeded`. The technician re-uploads a duplicate of a file that is fine and leaves the one that is actually missing. This is pre-existing, but this branch edits this create block, and the failure it produces is silent evidence loss in the same subsystem.

**Prescription.**
1. Both legs get an explicit `AbortSignal.timeout` budget — 90 s for the multipart, 20 s for the JSON leg — chosen so a stalled radio surfaces as a retryable error inside a technician's attention span rather than an indefinite spinner. Numbers are mine, not measured; overturn them with one field trial on the target network.
2. Replace `uploadingEvidence: boolean` with per-evidence-class in-flight state so one stalled upload cannot disable the others.
3. Persist `{blob, manifest, captureId, inspectionId, stepId, evidenceClass}` to IndexedDB *before* the first fetch and clear it only after step 2 returns 2xx. That is the §33 queue, and it is also what makes the byte-identical signed replay the module already documents actually possible.
4. Add a reconciliation query — `InspectionPhoto` rows with non-null `cocoaSha256` and no `EvidenceItem.sourcePhotoId` pointing at them — now trivial thanks to the new FK, exposed as an operational report rather than left invisible.
5. Fix `:291` to `.map((r, idx) => ...)` over an index-preserving pass (`createdItems.flatMap((r, idx) => r.status === "rejected" ? [{...}] : [])`), and add a test that fails file *k* of *n* for k>0.

## Unsigned evidence has no custody event and no durable replay identity

Two assertions someone can test. The first is false today, on the only path that runs in production.

**Assertion 1 — every non-REJECTED `EvidenceItem` has at least one `CustodyEvent` with `action = "CAPTURED"`.**

**[VERIFIED]** `grep -rn "custodyEvent.create" app lib` (excluding tests) returns exactly two sites, both in `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/app/api/inspections/[id]/evidence/route.ts`: `:448` inside the device-signed transaction, and `:580` for the `ARCHIVED` tombstone. The unsigned branch at `:261` — `const evidenceItem = await prisma.evidenceItem.create({` — creates the row and returns at `:294` with no custody event. The batch route creates rows with no custody event either.

So: every web-browser capture, every batch upload, and every native capture that fell back to unsigned produces an evidence item whose custody chain is empty. `buildEvidenceCustodyExport` will faithfully report `custodyPagination: {returnedCount: 0, totalCount: 0, complete: true}` — a truthful export of nothing. And signing is not available yet: **[VERIFIED]** `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/lib/native/device-signing.ts:23` — "physical-device behaviour (Keychain key generation and signing on real hardware) is validated only on hardware and remains the named blocker." Today, therefore, *no* evidence item in this system has a CAPTURED custody event, while `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/spec.md:282` requires "chain-of-custody on evidence". A dispute pack pulled next month ships evidence with an empty chain of custody, which is exactly the artefact the product exists to prevent.

Fix: move the unsigned create into a `$transaction` that also writes a `CAPTURED` custody event with `contentHash: storedPhoto.cocoaSha256`, `metadata: {integrity: "UNSIGNED"}`. The signed path already does this correctly at `:406-465`; the unsigned path is the one that was left behind — the half-finished migration METHOD.md §4 warns about.

**Assertion 2 — at most one non-REJECTED `EvidenceItem` per `(inspectionId, sourcePhotoId, evidenceClass)`.**

On the signed path the unique `captureReplayKey` enforces this durably. On the unsigned path there is no durable control at all: `captureReplayKey` is nullable and never set by `:261`, and Postgres unique indexes ignore NULLs. The only defence is the response cache — **[VERIFIED]** `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/lib/idempotency.ts:28` — `const TTL_MS = 24 * 60 * 60 * 1000; // 24h — matches Stripe`. The migration's own comment states the risk and then only solves it for signed rows: **[VERIFIED]** `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/prisma/migrations/20260725000000_ra7090_evidence_capture_replay_key/migration.sql:2` — "The IdempotencyRecord response cache expires after 24h; a queued offline capture can replay later than that".

**[INFERENCE]** This cannot bite today because no queue exists to replay after 24 h — which is precisely why it must be closed *before* the queue in finding 1 lands, not after. The condition that forces it back is the first durable replay of a capture; the mechanism is a partial unique index on `(inspectionId, sourcePhotoId, evidenceClass) WHERE status <> 'REJECTED' AND sourcePhotoId IS NOT NULL`, which is cheap now and requires a dedupe pass later.

## Nothing counts a fleet that stopped signing

`signCaptureManifest` correctly refuses to fabricate a signature and returns a truthful reason for each of five distinct failures. That reason then goes nowhere.

**[VERIFIED]** `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/lib/evidence/native-capture-upload.ts:64` — `unsignedReason?: DeviceSigningFallbackReason;` — is returned to the caller, and `grep -rn "unsignedReason" app lib components` (excluding tests) returns hits *only inside that module*. The sole caller destructures it away: **[VERIFIED]** `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/app/dashboard/inspections/[id]/capture/page.tsx:405` — `const { evidenceItem } = await uploadNativeCapture({` — followed at `:423` by `toast.success(\`${EVIDENCE_CLASS_LABELS[evidenceClass]} captured\`);`.

**The failure that will actually happen.** An iOS release ships with the plugin registered. A Keychain migration on an OS update, or an admin revoking one device key, or a build where `registerPlugin` silently resolves a proxy with no native side, turns `signCaptureManifest` into a `KEY_UNAVAILABLE`/`KEY_REVOKED`/`SIGNING_FAILED` generator. Every capture still succeeds. Every technician still sees a green toast. Every evidence row is written `UNSIGNED`, which is honest and useless. Nothing increments, nothing pages, and the discovery event is an insurer's lawyer asking why the fleet stopped producing tamper-evident captures on the 14th — months of claims later. This is the classic shape: it fails *closed* on truthfulness and *open* on detection, and the damage is unbounded in time because the signal for "this stopped happening" is an absence, which no error-rate dashboard can show.

**Prescription.** Emit one structured event per capture carrying `{inspectionId, integrity: "DEVICE_SIGNED" | "UNSIGNED", reason}` from `uploadNativeCapture`'s caller through `lib/observability.ts`. Alert on **absence**, not rate: once an organisation has recorded a `DEVICE_SIGNED` capture, page when its `DEVICE_SIGNED` count for a rolling 24 h falls to zero while total captures are non-zero. Also alert on any `KEY_REVOKED`, which means a device is still trying to sign with a key an admin killed. `/Users/phillmcgurk/restoreassist-ra7090-native-lidar-20260725/spec.md:294` says "alerts edge-triggered on state change" — this transition is exactly such an edge and currently emits nothing.

Not marked blocking: today every capture is unsigned by design, so there is no signal to lose yet. The condition that forces it back is the first production build with the iOS signing plugin registered — that release must not ship without the counter, because it is the release that creates something worth losing. **eng-observability may also answer this category; I am claiming it because the mechanism is fail-open-with-no-counter rather than instrumentation coverage, and I defer to their framing on the emitter.**
