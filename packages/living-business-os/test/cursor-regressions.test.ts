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

describe('Cursor-review regressions: consent, evidence and service boundaries', () => {
  it('does not accept marketing consent from an anonymous card scan', () => {
    const event = {
      organizationId: 'tenant-a',
      interactionId: 'evt-anon',
      channel: 'living_card',
      eventType: 'service_interest',
      serviceId: 'upholstery',
      happenedAt: now,
      pseudonymousSessionId: 'random-session',
      marketingConsent: true,
      source: {
        id: 'card-1',
        kind: 'card',
        capturedAt: now,
        dataClass: 'owned',
        organizationId: 'tenant-a',
      },
    };
    expect(customerInteractionSchema.safeParse(event).success).toBe(false);
    expect(
      customerInteractionSchema.safeParse({ ...event, crmContactId: 'c-1' })
        .success
    ).toBe(false);
    expect(
      customerInteractionSchema.safeParse({
        ...event,
        crmContactId: 'c-1',
        marketingConsentReceiptId: 'separate-opt-in-proof',
      }).success
    ).toBe(true);
    expect(
      customerInteractionSchema.safeParse({
        ...event,
        marketingConsent: false,
        marketingConsentReceiptId: 'proof',
      }).success
    ).toBe(false);
  });
  it('does not promote estimated demand even when mixed with one owned record', () => {
    const mixed = {
      ...signal,
      evidence: [
        signal.evidence[0],
        {
          id: 'competitor-1',
          kind: 'competitor_estimate' as const,
          capturedAt: now,
          dataClass: 'estimated' as const,
        },
      ],
    };
    expect(rankImprovements(intent, [mixed])[0].decision).toBe('research_more');
    expect(
      selectWeeklyQuestions(intent, [mixed]).some(
        x => x.id === 'verify_signal:signal-1'
      )
    ).toBe(true);
  });
  it('does not recommend a title that contains an excluded owner claim', () => {
    const guarded = {
      ...intent,
      constraints: { ...intent.constraints, excludedClaims: ['guaranteed'] },
    };
    const risky = { ...signal, title: 'Guaranteed mould removal' };
    const result = rankImprovements(guarded, [risky]);
    expect(result[0].decision).toBe('research_more');
    expect(result[0].reasons.join(' ')).toContain('owner-excluded');
  });
  it('does not ask the owner questions about services outside the catalogue', () => {
    expect(() =>
      selectWeeklyQuestions(intent, [{ ...signal, serviceId: 'unlisted' }])
    ).toThrow('UNKNOWN_SERVICE');
  });
  it('requires research when all working capacity is zero', () => {
    const zero = {
      ...intent,
      capacity: {
        ...intent.capacity,
        availableJobsPerWeek: 0,
        bookedJobsPerWeek: 0,
      },
    };
    expect(rankImprovements(zero, [signal])[0].decision).toBe(
      'defer_for_capacity'
    );
  });
});
