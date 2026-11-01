import { describe, expect, it } from 'vitest';
import { opportunitySignalSchema, businessIntentSchema } from '../src/contracts';
import { intent, signal } from './fixtures';

describe('non-finite numbers are rejected by direct calls (JSON cannot carry them)', () => {
  const bad = [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY];
  it.each(['confidence', 'risk', 'expectedGrossProfitAud', 'estimatedInterventionCostAud', 'expectedAdditionalJobsPerWeek'])('signal.%s', field => {
    for (const v of bad) {
      expect(opportunitySignalSchema.safeParse({ ...signal, [field]: v }).success, field + String(v)).toBe(false);
    }
  });
  it('intent maximumMonthlyAutomationCostAud', () => {
    for (const v of bad) {
      const r = businessIntentSchema.safeParse({ ...intent, constraints: { ...intent.constraints, maximumMonthlyAutomationCostAud: v } });
      expect(r.success).toBe(false);
    }
  });
  it('capacity counts', () => {
    for (const v of bad) {
      expect(businessIntentSchema.safeParse({ ...intent, capacity: { ...intent.capacity, availableJobsPerWeek: v } }).success).toBe(false);
    }
  });
  it('negative zero is accepted where zero is allowed', () => {
    expect(opportunitySignalSchema.safeParse({ ...signal, expectedGrossProfitAud: -0 }).success).toBe(true);
  });
});
