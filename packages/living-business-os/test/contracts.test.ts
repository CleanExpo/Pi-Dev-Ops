import {
  fulfilmentIdempotencyKey,
  fulfilmentRequestSchema,
  customerInteractionSchema,
  businessIntentSchema,
  opportunitySignalSchema,
} from '../src/contracts';
import { rankImprovements } from '../src/decision-engine';
import { selectWeeklyQuestions } from '../src/weekly-questions';
import { intent, signal, now } from './fixtures';

describe('Living Business OS contracts and first bounded engine', () => {
  it('rejects invalid/ambiguous orders and separates organisation idempotency', () => {
    const request = {
      sourceSystem: 'unite_group' as const,
      schemaVersion: 1 as const,
      externalOrderId: 'order-42',
      organizationId: 'tenant-a',
      approvedPackageId: 'basic',
      authorisationReceiptId: 'approval-7',
      requestedAssets: ['website' as const, 'crm' as const],
      issuedAt: now,
    };
    expect(fulfilmentRequestSchema.parse(request)).toEqual(request);
    expect(fulfilmentIdempotencyKey(request)).not.toBe(
      fulfilmentIdempotencyKey({ ...request, organizationId: 'tenant-b' })
    );
    expect(
      fulfilmentRequestSchema.safeParse({ ...request, unknown: true }).success
    ).toBe(false);
    expect(
      fulfilmentRequestSchema.safeParse({
        ...request,
        authorisationReceiptId: '',
      }).success
    ).toBe(false);
  });
  it('does not turn anonymous card attention into an identified lead', () => {
    const event = {
      organizationId: 'tenant-a',
      interactionId: 'evt-1',
      channel: 'living_card',
      eventType: 'service_interest',
      serviceId: 'upholstery',
      happenedAt: now,
      pseudonymousSessionId: 'random-session',
      source: {
        id: 'card-1',
        kind: 'card',
        capturedAt: now,
        dataClass: 'owned',
        organizationId: 'tenant-a',
      },
    };
    expect(customerInteractionSchema.safeParse(event).success).toBe(true);
    expect(
      customerInteractionSchema.safeParse({ ...event, eventType: 'sale' })
        .success
    ).toBe(false);
    expect(
      customerInteractionSchema.safeParse({
        ...event,
        eventType: 'sale',
        crmContactId: 'contact-1',
      }).success
    ).toBe(true);
  });
  it('always requires human approval for a good change', () => {
    const result = rankImprovements(intent, [signal]);
    expect(result).toHaveLength(1);
    expect(result[0].decision).toBe('draft_for_review');
    expect(result[0].approvalStatus).toBe('required');
    expect(result[0].priorityIndex).toBeGreaterThan(0);
  });
  it('halts a cross-tenant signal even if it looks profitable', () => {
    // A self-consistent tenant-b signal (its evidence is tenant-b too), so the
    // engine's own tenant check is what refuses it.
    const tenantB = {
      ...signal,
      organizationId: 'tenant-b',
      evidence: [{ ...signal.evidence[0], organizationId: 'tenant-b' }],
    };
    expect(() => rankImprovements(intent, [tenantB])).toThrow(
      'TENANT_MISMATCH'
    );
    expect(() => selectWeeklyQuestions(intent, [tenantB])).toThrow(
      'TENANT_MISMATCH'
    );
  });
  it('does not boost demand beyond capacity', () => {
    const result = rankImprovements(
      { ...intent, capacity: { ...intent.capacity, bookedJobsPerWeek: 10 } },
      [signal]
    );
    expect(result[0].decision).toBe('defer_for_capacity');
    expect(result[0].reasons.join(' ')).toContain('capacity');
  });
  it('does not treat competitor estimates as verified sales', () => {
    const result = rankImprovements(intent, [
      {
        ...signal,
        evidence: [
          {
            ...signal.evidence[0],
            dataClass: 'estimated',
            kind: 'competitor_estimate',
          },
        ],
      },
    ]);
    expect(result[0].decision).toBe('research_more');
  });
  it('never assumes free capacity when unknown and respects spend allowance', () => {
    expect(
      rankImprovements(
        {
          ...intent,
          capacity: {
            availableJobsPerWeek: null,
            bookedJobsPerWeek: null,
            updatedAt: null,
          },
        },
        [signal]
      )[0].decision
    ).toBe('research_more');
    expect(
      rankImprovements(intent, [
        { ...signal, estimatedInterventionCostAud: 150 },
      ])[0].decision
    ).toBe('research_more');
  });
  it('generates at most 3 evidence-driven voice questions, avoids repeats, permits zero', () => {
    const incomplete = {
      ...intent,
      capacity: {
        availableJobsPerWeek: null,
        bookedJobsPerWeek: null,
        updatedAt: null,
      },
    };
    const weak = { ...signal, confidence: 0.3 };
    const q = selectWeeklyQuestions(incomplete, [weak]);
    expect(q.length).toBeLessThanOrEqual(3);
    expect(q[0].id).toBe('capacity_current');
    expect(
      selectWeeklyQuestions(incomplete, [weak], new Set(q.map(x => x.id)))
    ).toEqual([]);
    const complete = {
      ...intent,
      constraints: { ...intent.constraints, preferredServices: ['upholstery'] },
    };
    expect(selectWeeklyQuestions(complete, [signal])).toEqual([]);
  });
  it('rejects a malformed intent and conflicting signal ids', () => {
    expect(
      businessIntentSchema.safeParse({
        ...intent,
        constraints: { ...intent.constraints, publishing: 'automatic' },
      }).success
    ).toBe(false);
    expect(() =>
      rankImprovements(intent, [signal, { ...signal, title: 'different' }])
    ).toThrow('CONFLICTING_SIGNAL_ID');
  });
});
