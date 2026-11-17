import type { components } from './api.generated';

export type Session = components['schemas']['Session'];
export type Artifact = components['schemas']['Artifact'];
export type SessionEvent = components['schemas']['SessionEvent'];
export type Bootstrap = components['schemas']['BootstrapResponse'];
export type ModuleDescriptor = components['schemas']['ModuleDescriptor'];

export type ErrorBody = components['schemas']['ErrorBody'];
export type CreateSession = components['schemas']['CreateSession'];
export type SendMessage = components['schemas']['SendMessage'];
export type StopRun = components['schemas']['StopRun'];

export type ActionRequest = components['schemas']['ActionRequest'];
export type PolicyDecision = components['schemas']['PolicyDecision'];

export type ModelInfo = components['schemas']['ModelInfo'];
export type ModelResult = components['schemas']['ModelResult'];

export type JudgmentInfo = components['schemas']['JudgmentInfo'];
export type JudgmentResult = components['schemas']['JudgmentResult'];
