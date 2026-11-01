// Shared fixtures from the Synthex test file (lines 13-48 at 5445287f7).
import type { BusinessIntent, OpportunitySignal } from '../src/contracts';

export const now = '2026-10-27T08:00:00+10:00';
export const intent: BusinessIntent = {
  organizationId: 'tenant-a',
  businessName: 'Example Carpet Care',
  goals: ['profitable repeat business'],
  serviceIds: ['upholstery'],
  capacity: { availableJobsPerWeek: 10, bookedJobsPerWeek: 8, updatedAt: now },
  constraints: {
    preferredServices: [],
    excludedClaims: [],
    maximumMonthlyAutomationCostAud: 100,
    publishing: 'approval_required',
    customerDataReuse: 'tenant_only',
  },
};
export const signal: OpportunitySignal = {
  id: 'signal-1',
  organizationId: 'tenant-a',
  serviceId: 'upholstery',
  title: 'Interest in upholstery cleaning',
  evidence: [
    {
      id: 'crm-1',
      kind: 'crm',
      capturedAt: now,
      dataClass: 'owned',
      organizationId: 'tenant-a',
    },
  ],
  confidence: 0.8,
  risk: 0.2,
  expectedGrossProfitAud: 300,
  estimatedInterventionCostAud: 40,
  expectedAdditionalJobsPerWeek: 1,
  outcomeMetric: 'verified gross profit from upholstery enquiries',
  observedAt: now,
};
