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

export type ToolDescriptor = components['schemas']['ToolDescriptor'];
export type ToolPrepareCommand = components['schemas']['ToolPrepareCommand'];
export type ToolPlan = components['schemas']['ToolPlan'];
export type ToolApproval = components['schemas']['ToolApproval'];
export type ToolReceipt = components['schemas']['ToolReceipt'];
export type WorkspaceView = components['schemas']['WorkspaceView'];

export type Asset = components['schemas']['Asset-Output'];
export type Project = components['schemas']['Project-Output'];
export type AssetRevision = components['schemas']['Revision'];
export type Snapshot = components['schemas']['Snapshot'];
export type VersionInfo = components['schemas']['VersionInfo'];

export type ContextSnapshot = components['schemas']['ContextSnapshot'];
export type ContextPreviewCommand = components['schemas']['ContextPreviewCommand'];

export type AgentRun = components['schemas']['AgentRun'];
export type CreateRun = components['schemas']['CreateRun-Input'];
export type RunCommand = components['schemas']['RunCommand'];

export type Trajectory = components['schemas']['Trajectory'];
export type RecoveryCommand = components['schemas']['RecoveryCommand'];

export type RunFrame = components['schemas']['RunFrame'];

export type RunSnapshot = components['schemas']['RunSnapshot'];

export type UploadCommand = components['schemas']['UploadCommand'];

export type UploadIntent = components['schemas']['UploadIntent'];

export type UploadReceipt = components['schemas']['UploadReceipt'];

export type RunPage = components['schemas']['RunPage'];

export type FeedbackCommand = components['schemas']['FeedbackCommand'];

export type FeedbackReceipt = components['schemas']['FeedbackReceipt'];

export type AssessmentStatus = components['schemas']['AssessmentStatus'];

export type EvalJob = components['schemas']['EvalJob'];

export type EvalReport = components['schemas']['EvalReport'];

export type Aggregate = components['schemas']['Aggregate'];

export type CalibrationReport = components['schemas']['CalibrationReport'];

export type CaseBank = components['schemas']['CaseBank'];

export type WindowView = components['schemas']['WindowView'];

export type BlindWindow = components['schemas']['BlindWindow'];

export type BlindWindowCommand = components['schemas']['BlindWindowCommand'];

export type CalibrationCommand = components['schemas']['CalibrationCommand'];

export type ImportCases = components['schemas']['ImportCases'];

export type SeedCommand = components['schemas']['SeedCommand'];

export type Comparison = components['schemas']['Comparison'];

export type CompareCommand = components['schemas']['CompareCommand'];

export type BatchEvaluation = components['schemas']['BatchEvaluation'];

export type BatchResult = components['schemas']['BatchResult'];

export type EvaluateCommand = components['schemas']['EvaluateCommand-Input'];

export type DelegationView = components['schemas']['DelegationView'];

export type DelegationCommand = components['schemas']['DelegationCommand'];

export type DelegationStatus = components['schemas']['DelegationStatus'];

export type ContrastCommand = components['schemas']['ContrastCommand'];

export type SingleMultiContrast = components['schemas']['SingleMultiContrast'];

export type DelegationCreate = components['schemas']['DelegationCreate-Input'];
