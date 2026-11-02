"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/index.ts
var index_exports = {};
__export(index_exports, {
  ALLOWED_DATA_CLASSES: () => ALLOWED_DATA_CLASSES,
  CONTRACT_VERSION: () => CONTRACT_VERSION,
  businessIntentSchema: () => businessIntentSchema,
  customerInteractionSchema: () => customerInteractionSchema,
  fulfilmentIdempotencyKey: () => fulfilmentIdempotencyKey,
  fulfilmentRequestSchema: () => fulfilmentRequestSchema,
  opportunitySignalSchema: () => opportunitySignalSchema,
  rankImprovements: () => rankImprovements,
  selectWeeklyQuestions: () => selectWeeklyQuestions
});
module.exports = __toCommonJS(index_exports);

// src/contracts.ts
var import_zod = require("zod");
var nonEmpty = import_zod.z.string().trim().min(1);
var evidenceKinds = [
  "owned_analytics",
  "crm",
  "card",
  "phone",
  "search_console",
  "competitor_estimate",
  "owner_answer",
  "research"
];
var dataClasses = [
  "public",
  "owned",
  "client_approved",
  "estimated"
];
var ALLOWED_DATA_CLASSES = {
  owned_analytics: ["owned"],
  crm: ["owned", "client_approved"],
  card: ["owned"],
  phone: ["owned", "client_approved"],
  search_console: ["owned"],
  competitor_estimate: ["estimated"],
  owner_answer: ["client_approved", "owned"],
  research: ["public", "estimated"]
};
var PRIVATE_DATA_CLASSES = ["owned", "client_approved"];
var sourceRef = import_zod.z.object({
  id: nonEmpty,
  kind: import_zod.z.enum(evidenceKinds),
  capturedAt: import_zod.z.string().datetime({ offset: true }),
  dataClass: import_zod.z.enum(dataClasses),
  /** Required for private (owned / client_approved) evidence; tenant-scoped. */
  organizationId: nonEmpty.optional(),
  sourceUrl: import_zod.z.string().url().optional()
}).strict().superRefine((v, ctx) => {
  if (!ALLOWED_DATA_CLASSES[v.kind].includes(v.dataClass)) {
    ctx.addIssue({
      code: "custom",
      path: ["dataClass"],
      message: `Evidence kind ${v.kind} cannot carry data class ${v.dataClass} (provenance mismatch)`
    });
  }
  if (PRIVATE_DATA_CLASSES.includes(v.dataClass) && !v.organizationId) {
    ctx.addIssue({
      code: "custom",
      path: ["organizationId"],
      message: "Private evidence (owned or client_approved) must name its organisation"
    });
  }
});
function refuseForeignEvidence(organizationId, refs, ctx) {
  for (const { ref, path } of refs) {
    if (ref.organizationId !== void 0 && ref.organizationId !== organizationId) {
      ctx.addIssue({
        code: "custom",
        path: [...path, "organizationId"],
        message: "Evidence belongs to another tenant; cross-tenant references are refused"
      });
    }
  }
}
var businessIntentSchema = import_zod.z.object({
  organizationId: nonEmpty,
  businessName: nonEmpty,
  goals: import_zod.z.array(nonEmpty).min(1).max(10),
  serviceIds: import_zod.z.array(nonEmpty).min(1),
  capacity: import_zod.z.object({
    availableJobsPerWeek: import_zod.z.number().int().nonnegative().nullable(),
    bookedJobsPerWeek: import_zod.z.number().int().nonnegative().nullable(),
    updatedAt: import_zod.z.string().datetime({ offset: true }).nullable()
  }).strict(),
  constraints: import_zod.z.object({
    preferredServices: import_zod.z.array(nonEmpty).default([]),
    excludedClaims: import_zod.z.array(nonEmpty).default([]),
    maximumMonthlyAutomationCostAud: import_zod.z.number().finite().nonnegative(),
    publishing: import_zod.z.literal("approval_required"),
    customerDataReuse: import_zod.z.literal("tenant_only")
  }).strict()
}).strict();
var opportunitySignalSchema = import_zod.z.object({
  id: nonEmpty,
  organizationId: nonEmpty,
  serviceId: nonEmpty,
  title: nonEmpty,
  evidence: import_zod.z.array(sourceRef).min(1),
  confidence: import_zod.z.number().finite().min(0).max(1),
  risk: import_zod.z.number().finite().min(0).max(1),
  expectedGrossProfitAud: import_zod.z.number().finite().nonnegative(),
  estimatedInterventionCostAud: import_zod.z.number().finite().nonnegative(),
  expectedAdditionalJobsPerWeek: import_zod.z.number().finite().nonnegative(),
  outcomeMetric: nonEmpty,
  observedAt: import_zod.z.string().datetime({ offset: true })
}).strict().superRefine(
  (v, ctx) => refuseForeignEvidence(
    v.organizationId,
    v.evidence.map((ref, i) => ({ ref, path: ["evidence", i] })),
    ctx
  )
);
var fulfilmentRequestSchema = import_zod.z.object({
  sourceSystem: import_zod.z.literal("unite_group"),
  schemaVersion: import_zod.z.literal(1),
  externalOrderId: nonEmpty,
  organizationId: nonEmpty,
  approvedPackageId: nonEmpty,
  /** Created by server-side order verification; never trust browser claims. */
  authorisationReceiptId: nonEmpty,
  requestedAssets: import_zod.z.array(import_zod.z.enum(["website", "crm", "living_card", "owner_dashboard"])).min(1),
  issuedAt: import_zod.z.string().datetime({ offset: true })
}).strict();
function fulfilmentIdempotencyKey(request) {
  const parsed = fulfilmentRequestSchema.parse(request);
  return [parsed.sourceSystem, parsed.organizationId, parsed.externalOrderId].map(encodeURIComponent).join(":");
}
var customerInteractionSchema = import_zod.z.object({
  organizationId: nonEmpty,
  interactionId: nonEmpty,
  channel: import_zod.z.enum(["website", "living_card", "phone", "crm"]),
  eventType: import_zod.z.enum([
    "service_interest",
    "enquiry",
    "booking",
    "sale",
    "repeat_sale"
  ]),
  serviceId: nonEmpty,
  happenedAt: import_zod.z.string().datetime({ offset: true }),
  pseudonymousSessionId: nonEmpty.optional(),
  crmContactId: nonEmpty.optional(),
  marketingConsent: import_zod.z.boolean().default(false),
  marketingConsentReceiptId: nonEmpty.optional(),
  source: sourceRef
}).strict().superRefine((v, ctx) => {
  refuseForeignEvidence(
    v.organizationId,
    [{ ref: v.source, path: ["source"] }],
    ctx
  );
  if (v.eventType !== "service_interest" && !v.crmContactId) {
    ctx.addIssue({
      code: "custom",
      path: ["crmContactId"],
      message: "Personalised lifecycle actions need a linked, authorised CRM contact"
    });
  }
  if (v.marketingConsent && (!v.crmContactId || !v.marketingConsentReceiptId)) {
    ctx.addIssue({
      code: "custom",
      path: ["marketingConsent"],
      message: "Direct marketing requires a verified contact and a separate consent receipt; event data alone is not proof"
    });
  }
  if (!v.marketingConsent && v.marketingConsentReceiptId) {
    ctx.addIssue({
      code: "custom",
      path: ["marketingConsentReceiptId"],
      message: "Consent receipt cannot be attached to a non-consenting interaction"
    });
  }
});

// src/decision-engine.ts
function rankImprovements(intentInput, rawSignals) {
  const intent = businessIntentSchema.parse(intentInput);
  const availableCapacity = intent.capacity.availableJobsPerWeek;
  const bookedCapacity = intent.capacity.bookedJobsPerWeek;
  const capacityKnown = availableCapacity !== null && bookedCapacity !== null;
  const noCapacity = capacityKnown && bookedCapacity >= availableCapacity;
  const deduplicated = /* @__PURE__ */ new Map();
  for (const candidate of rawSignals) {
    const s = opportunitySignalSchema.parse(candidate);
    if (s.organizationId !== intent.organizationId) {
      throw new Error("TENANT_MISMATCH");
    }
    if (!intent.serviceIds.includes(s.serviceId)) {
      throw new Error("UNKNOWN_SERVICE");
    }
    const prior = deduplicated.get(s.id);
    if (prior && JSON.stringify(prior) !== JSON.stringify(s)) {
      throw new Error("CONFLICTING_SIGNAL_ID");
    }
    deduplicated.set(s.id, s);
  }
  const proposals = Array.from(deduplicated.values()).map((s) => {
    const reasons = [];
    const evidenceRefs = s.evidence.map((e) => e.id);
    const weakEvidence = s.confidence < 0.65 || s.evidence.some((e) => e.dataClass === "estimated");
    const highRisk = s.risk >= 0.6;
    const prohibitedClaim = intent.constraints.excludedClaims.some(
      (claim) => [s.title, s.outcomeMetric].some(
        (text) => text.toLocaleLowerCase().includes(claim.toLocaleLowerCase())
      )
    );
    const netPotential = s.expectedGrossProfitAud - s.estimatedInterventionCostAud;
    const exceedsBudget = s.estimatedInterventionCostAud > intent.constraints.maximumMonthlyAutomationCostAud;
    if (weakEvidence)
      reasons.push(
        "Evidence insufficient for an intervention; verify with owned data."
      );
    if (highRisk)
      reasons.push("Elevated intervention risk requires additional review.");
    if (prohibitedClaim)
      reasons.push(
        "Opportunity contains an owner-excluded marketing claim; revise before considering a draft."
      );
    if (exceedsBudget)
      reasons.push("Estimated cost exceeds the client automation allowance.");
    if (netPotential <= 0)
      reasons.push("Estimated gross profit does not exceed intervention cost.");
    if (!capacityKnown)
      reasons.push(
        "Owner capacity is unknown; confirm before demand generation."
      );
    if (noCapacity && s.expectedAdditionalJobsPerWeek > 0)
      reasons.push(
        "Booked capacity is full; preserve organic visibility and consider future bookings."
      );
    if (intent.constraints.preferredServices.length && !intent.constraints.preferredServices.includes(s.serviceId)) {
      reasons.push("Service is not among the owner\u2019s preferred priorities.");
    }
    const decision = noCapacity && s.expectedAdditionalJobsPerWeek > 0 ? "defer_for_capacity" : weakEvidence || highRisk || prohibitedClaim || exceedsBudget || netPotential <= 0 || !capacityKnown ? "research_more" : "draft_for_review";
    const priorityIndex = Math.round(
      (netPotential > 0 ? Math.log1p(netPotential) : 0) * s.confidence * (1 - s.risk) * 100
    ) / 100;
    return {
      signalId: s.id,
      organizationId: s.organizationId,
      serviceId: s.serviceId,
      title: s.title,
      outcomeMetric: s.outcomeMetric,
      priorityIndex,
      expectedGrossProfitAud: s.expectedGrossProfitAud,
      estimatedInterventionCostAud: s.estimatedInterventionCostAud,
      decision,
      reasons,
      evidenceRefs,
      approvalStatus: "required"
    };
  });
  return proposals.sort(
    (a, b) => b.priorityIndex - a.priorityIndex || a.signalId.localeCompare(b.signalId)
  );
}

// src/weekly-questions.ts
function selectWeeklyQuestions(intentInput, rawSignals, answeredQuestionIds = /* @__PURE__ */ new Set()) {
  const intent = businessIntentSchema.parse(intentInput);
  const signals = rawSignals.map((s) => opportunitySignalSchema.parse(s));
  if (signals.some((s) => s.organizationId !== intent.organizationId)) {
    throw new Error("TENANT_MISMATCH");
  }
  if (signals.some((s) => !intent.serviceIds.includes(s.serviceId))) {
    throw new Error("UNKNOWN_SERVICE");
  }
  const candidates = [];
  const cap = intent.capacity;
  if (cap.availableJobsPerWeek === null || cap.bookedJobsPerWeek === null) {
    candidates.push({
      id: "capacity_current",
      priority: 100,
      text: "How many jobs can your team take next week, and how many are already booked?",
      purpose: "Avoid sending more work than the business can fulfil."
    });
  }
  if (cap.availableJobsPerWeek !== null && cap.bookedJobsPerWeek !== null && cap.bookedJobsPerWeek > cap.availableJobsPerWeek) {
    candidates.push({
      id: "capacity_overrun",
      priority: 95,
      text: "You appear over capacity. Should we focus on future bookings or higher-value work?",
      purpose: "Preserve customer trust and margins when demand exceeds capacity."
    });
  }
  if (intent.constraints.preferredServices.length === 0) {
    candidates.push({
      id: "service_priorities",
      priority: 80,
      text: "Which services do you most want to be known for, based on your quality and profitability?",
      purpose: "Guide customer fit rather than maximising enquiry volume."
    });
  }
  for (const signal of signals) {
    if (signal.confidence < 0.65 || signal.evidence.some((e) => e.dataClass === "estimated")) {
      candidates.push({
        id: `verify_signal:${signal.id}`,
        priority: 70 + Math.round(signal.confidence * 10),
        text: `We're seeing a possible opportunity for ${signal.serviceId}. Are customers actually requesting this service, and what do they value most about it?`,
        purpose: "Validate an estimated opportunity before altering marketing.",
        signalId: signal.id
      });
    }
  }
  return candidates.filter((q) => !answeredQuestionIds.has(q.id)).sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id)).slice(0, 3);
}

// src/index.ts
var CONTRACT_VERSION = "lbos.contracts.v1";
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  ALLOWED_DATA_CLASSES,
  CONTRACT_VERSION,
  businessIntentSchema,
  customerInteractionSchema,
  fulfilmentIdempotencyKey,
  fulfilmentRequestSchema,
  opportunitySignalSchema,
  rankImprovements,
  selectWeeklyQuestions
});
