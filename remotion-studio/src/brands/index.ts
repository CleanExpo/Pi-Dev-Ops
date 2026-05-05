// Re-export shim. Source of truth lives at @unite-group/brand-config.
// Existing consumers (`from '../brands'`, `from './brands/types'`) continue working
// unchanged; this file forwards to the package without behavioural change.
export * from '@unite-group/brand-config';
