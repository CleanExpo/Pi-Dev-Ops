// Public surface of @unite-group/living-business-os. The three rule files are
// byte-identical to Synthex 5445287f7; this file only re-exports them.
export {
  ALLOWED_DATA_CLASSES,
  businessIntentSchema,
  opportunitySignalSchema,
  fulfilmentRequestSchema,
  fulfilmentIdempotencyKey,
  customerInteractionSchema,
} from './contracts';
export type {
  BusinessIntent,
  OpportunitySignal,
  FulfilmentRequest,
  CustomerInteraction,
} from './contracts';
export { rankImprovements } from './decision-engine';
export type { ImprovementProposal } from './decision-engine';
export { selectWeeklyQuestions } from './weekly-questions';
export type { OwnerQuestion } from './weekly-questions';

export const CONTRACT_VERSION = 'lbos.contracts.v1';
