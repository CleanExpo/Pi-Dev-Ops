import {
  fulfilmentIdempotencyKey,
  fulfilmentRequestSchema,
  customerInteractionSchema,
  businessIntentSchema,
  opportunitySignalSchema,
} from '../src/contracts';
import { rankImprovements } from '../src/decision-engine';
import { selectWeeklyQuestions } from '../src/weekly-questions';
import type { OpportunitySignal } from '../src/contracts';
import { intent, signal, now } from './fixtures';

describe('Codex exact-SHA review regressions (RA-8145): provenance and tenant scope of evidence', () => {
  // Each case asserts the specific rule's message, so a parse failure for an
  // unrelated reason (for example an unknown key under .strict()) cannot pass it.
  const messages = (r: {
    success: boolean;
    error?: { issues: { message: string }[] };
  }) =>
    r.success ? '' : (r.error?.issues ?? []).map(i => i.message).join(' | ');
  const tenantEvidence = {
    id: 'crm-1',
    kind: 'crm' as const,
    capturedAt: now,
    dataClass: 'owned' as const,
    organizationId: 'tenant-a',
  };
  const scoped = { ...signal, evidence: [tenantEvidence] };

  it('rejects a competitor estimate labelled as owned data (review repro)', () => {
    const laundered = {
      ...signal,
      evidence: [
        {
          id: 'competitor-1',
          kind: 'competitor_estimate',
          capturedAt: now,
          dataClass: 'owned',
        },
      ],
    } as unknown as OpportunitySignal;
    expect(messages(opportunitySignalSchema.safeParse(laundered))).toContain(
      'provenance mismatch'
    );
    expect(() => rankImprovements(intent, [laundered])).toThrow(
      /provenance mismatch/
    );
    expect(() => selectWeeklyQuestions(intent, [laundered])).toThrow(
      /provenance mismatch/
    );
  });

  it('rejects research evidence claiming to be owned or client-approved', () => {
    for (const dataClass of ['owned', 'client_approved']) {
      const bad = {
        ...signal,
        evidence: [
          { id: 'research-1', kind: 'research', capturedAt: now, dataClass },
        ],
      };
      expect(messages(opportunitySignalSchema.safeParse(bad))).toContain(
        'provenance mismatch'
      );
    }
  });

  it('requires private evidence to name its organisation', () => {
    const unscoped = {
      ...signal,
      evidence: [
        { id: 'crm-1', kind: 'crm', capturedAt: now, dataClass: 'owned' },
      ],
    };
    expect(messages(opportunitySignalSchema.safeParse(unscoped))).toContain(
      'must name its organisation'
    );
    expect(
      messages(
        customerInteractionSchema.safeParse({
          organizationId: 'tenant-a',
          interactionId: 'evt-u',
          channel: 'living_card',
          eventType: 'service_interest',
          serviceId: 'upholstery',
          happenedAt: now,
          source: {
            id: 'card-1',
            kind: 'card',
            capturedAt: now,
            dataClass: 'owned',
          },
        })
      )
    ).toContain('must name its organisation');
  });

  it('refuses evidence that belongs to another tenant (review repro)', () => {
    const crossTenant = {
      ...scoped,
      evidence: [
        {
          ...tenantEvidence,
          id: 'tenant-b/crm-contact-1',
          organizationId: 'tenant-b',
        },
      ],
    };
    expect(messages(opportunitySignalSchema.safeParse(crossTenant))).toContain(
      'another tenant'
    );
    expect(() => rankImprovements(intent, [crossTenant])).toThrow(
      /another tenant/
    );
    expect(() => selectWeeklyQuestions(intent, [crossTenant])).toThrow(
      /another tenant/
    );
  });

  it('refuses a customer interaction whose source belongs to another tenant', () => {
    const event = {
      organizationId: 'tenant-a',
      interactionId: 'evt-x',
      channel: 'living_card',
      eventType: 'service_interest',
      serviceId: 'upholstery',
      happenedAt: now,
      source: {
        ...tenantEvidence,
        kind: 'card' as const,
        id: 'card-1',
        organizationId: 'tenant-b',
      },
    };
    expect(messages(customerInteractionSchema.safeParse(event))).toContain(
      'another tenant'
    );
    expect(
      customerInteractionSchema.safeParse({
        ...event,
        source: { ...event.source, organizationId: 'tenant-a' },
      }).success
    ).toBe(true);
  });

  it('still accepts correctly scoped owned evidence and public research', () => {
    const ok = {
      ...scoped,
      evidence: [
        tenantEvidence,
        {
          id: 'r-1',
          kind: 'research' as const,
          capturedAt: now,
          dataClass: 'public' as const,
        },
      ],
    };
    expect(opportunitySignalSchema.safeParse(ok).success).toBe(true);
    expect(rankImprovements(intent, [ok])[0].decision).toBe('draft_for_review');
  });
});
