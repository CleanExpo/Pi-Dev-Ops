import { describe, expect, it } from 'vitest';
import { businessIntentSchema } from '../src/contracts';
import { intent } from './fixtures';

// Mutant (e) control: written first and red when publishing: z.literal('approval_required') becomes z.string().
describe('publishing approval is part of the contract', () => {
  it('rejects an intent that does not require publishing approval', () => {
    for (const publishing of ['automatic', 'auto_publish', '', 'approval-required']) {
      const r = businessIntentSchema.safeParse({ ...intent, constraints: { ...intent.constraints, publishing } });
      expect(r.success).toBe(false);
      const paths = r.success ? [] : r.error.issues.map(i => i.path.join('.'));
      expect(paths).toContain('constraints.publishing');
    }
  });
  it('accepts approval_required', () => {
    expect(businessIntentSchema.safeParse(intent).success).toBe(true);
  });
});
