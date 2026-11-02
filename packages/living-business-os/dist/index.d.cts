import { z } from 'zod';

/**
 * SYN-1316 Living Business OS: internal contracts, not a second database.
 * Boundaries: Unite Group owns order/billing; Synthex owns authorised
 * fulfilment and drafts. These shapes are intentionally provider-neutral.
 */

declare const evidenceKinds: readonly ["owned_analytics", "crm", "card", "phone", "search_console", "competitor_estimate", "owner_answer", "research"];
declare const dataClasses: readonly ["public", "owned", "client_approved", "estimated"];
type EvidenceKind = (typeof evidenceKinds)[number];
type DataClass = (typeof dataClasses)[number];
/**
 * Provenance: which data classes each evidence kind may honestly carry. A
 * competitor estimate is always an estimate and research is never the
 * tenant's own data, so a label cannot promote either past the estimate gate.
 */
declare const ALLOWED_DATA_CLASSES: Readonly<Record<EvidenceKind, readonly DataClass[]>>;
declare const businessIntentSchema: z.ZodObject<{
    organizationId: z.ZodString;
    businessName: z.ZodString;
    goals: z.ZodArray<z.ZodString>;
    serviceIds: z.ZodArray<z.ZodString>;
    capacity: z.ZodObject<{
        availableJobsPerWeek: z.ZodNullable<z.ZodNumber>;
        bookedJobsPerWeek: z.ZodNullable<z.ZodNumber>;
        updatedAt: z.ZodNullable<z.ZodString>;
    }, z.core.$strict>;
    constraints: z.ZodObject<{
        preferredServices: z.ZodDefault<z.ZodArray<z.ZodString>>;
        excludedClaims: z.ZodDefault<z.ZodArray<z.ZodString>>;
        maximumMonthlyAutomationCostAud: z.ZodNumber;
        publishing: z.ZodLiteral<"approval_required">;
        customerDataReuse: z.ZodLiteral<"tenant_only">;
    }, z.core.$strict>;
}, z.core.$strict>;
type BusinessIntent = z.infer<typeof businessIntentSchema>;
declare const opportunitySignalSchema: z.ZodObject<{
    id: z.ZodString;
    organizationId: z.ZodString;
    serviceId: z.ZodString;
    title: z.ZodString;
    evidence: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        kind: z.ZodEnum<{
            owned_analytics: "owned_analytics";
            crm: "crm";
            card: "card";
            phone: "phone";
            search_console: "search_console";
            competitor_estimate: "competitor_estimate";
            owner_answer: "owner_answer";
            research: "research";
        }>;
        capturedAt: z.ZodString;
        dataClass: z.ZodEnum<{
            public: "public";
            owned: "owned";
            client_approved: "client_approved";
            estimated: "estimated";
        }>;
        organizationId: z.ZodOptional<z.ZodString>;
        sourceUrl: z.ZodOptional<z.ZodString>;
    }, z.core.$strict>>;
    confidence: z.ZodNumber;
    risk: z.ZodNumber;
    expectedGrossProfitAud: z.ZodNumber;
    estimatedInterventionCostAud: z.ZodNumber;
    expectedAdditionalJobsPerWeek: z.ZodNumber;
    outcomeMetric: z.ZodString;
    observedAt: z.ZodString;
}, z.core.$strict>;
type OpportunitySignal = z.infer<typeof opportunitySignalSchema>;
declare const fulfilmentRequestSchema: z.ZodObject<{
    sourceSystem: z.ZodLiteral<"unite_group">;
    schemaVersion: z.ZodLiteral<1>;
    externalOrderId: z.ZodString;
    organizationId: z.ZodString;
    approvedPackageId: z.ZodString;
    authorisationReceiptId: z.ZodString;
    requestedAssets: z.ZodArray<z.ZodEnum<{
        crm: "crm";
        website: "website";
        living_card: "living_card";
        owner_dashboard: "owner_dashboard";
    }>>;
    issuedAt: z.ZodString;
}, z.core.$strict>;
type FulfilmentRequest = z.infer<typeof fulfilmentRequestSchema>;
/** Deterministic idempotency scope: prevent cross-client order collisions. */
declare function fulfilmentIdempotencyKey(request: FulfilmentRequest): string;
/**
 * Customer enquiries require separate consent and identity checks.
 * Anonymous card attention is NOT a CRM contact nor marketing consent.
 */
declare const customerInteractionSchema: z.ZodObject<{
    organizationId: z.ZodString;
    interactionId: z.ZodString;
    channel: z.ZodEnum<{
        crm: "crm";
        phone: "phone";
        website: "website";
        living_card: "living_card";
    }>;
    eventType: z.ZodEnum<{
        service_interest: "service_interest";
        enquiry: "enquiry";
        booking: "booking";
        sale: "sale";
        repeat_sale: "repeat_sale";
    }>;
    serviceId: z.ZodString;
    happenedAt: z.ZodString;
    pseudonymousSessionId: z.ZodOptional<z.ZodString>;
    crmContactId: z.ZodOptional<z.ZodString>;
    marketingConsent: z.ZodDefault<z.ZodBoolean>;
    marketingConsentReceiptId: z.ZodOptional<z.ZodString>;
    source: z.ZodObject<{
        id: z.ZodString;
        kind: z.ZodEnum<{
            owned_analytics: "owned_analytics";
            crm: "crm";
            card: "card";
            phone: "phone";
            search_console: "search_console";
            competitor_estimate: "competitor_estimate";
            owner_answer: "owner_answer";
            research: "research";
        }>;
        capturedAt: z.ZodString;
        dataClass: z.ZodEnum<{
            public: "public";
            owned: "owned";
            client_approved: "client_approved";
            estimated: "estimated";
        }>;
        organizationId: z.ZodOptional<z.ZodString>;
        sourceUrl: z.ZodOptional<z.ZodString>;
    }, z.core.$strict>;
}, z.core.$strict>;
type CustomerInteraction = z.infer<typeof customerInteractionSchema>;

/**
 * SYN-1316 deterministic decision layer. It drafts; it never publishes.
 * Financial impact is an estimate until outcome measurement validates it.
 */

interface ImprovementProposal {
    signalId: string;
    organizationId: string;
    serviceId: string;
    title: string;
    outcomeMetric: string;
    /** Ranking index is not profit nor a causal effect estimate. */
    priorityIndex: number;
    expectedGrossProfitAud: number;
    estimatedInterventionCostAud: number;
    decision: 'draft_for_review' | 'research_more' | 'defer_for_capacity';
    reasons: string[];
    evidenceRefs: string[];
    approvalStatus: 'required';
}
declare function rankImprovements(intentInput: BusinessIntent, rawSignals: OpportunitySignal[]): ImprovementProposal[];

/**
 * SYN-1316 weekly owner voice check-in: questions derive from missing
 * decision-critical facts. Zero is valid when all facts are adequate.
 */

interface OwnerQuestion {
    id: string;
    priority: number;
    text: string;
    purpose: string;
    signalId?: string;
}
declare function selectWeeklyQuestions(intentInput: BusinessIntent, rawSignals: OpportunitySignal[], answeredQuestionIds?: ReadonlySet<string>): OwnerQuestion[];

declare const CONTRACT_VERSION = "lbos.contracts.v1";

export { ALLOWED_DATA_CLASSES, type BusinessIntent, CONTRACT_VERSION, type CustomerInteraction, type FulfilmentRequest, type ImprovementProposal, type OpportunitySignal, type OwnerQuestion, businessIntentSchema, customerInteractionSchema, fulfilmentIdempotencyKey, fulfilmentRequestSchema, opportunitySignalSchema, rankImprovements, selectWeeklyQuestions };
