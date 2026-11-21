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

export type EvolutionStatus = components['schemas']['EvolutionStatus'];

export type Diagnosis = components['schemas']['Diagnosis'];

export type DiagnoseCommand = components['schemas']['DiagnoseCommand'];

export type Proposal = components['schemas']['Proposal'];

export type ProposalCommand = components['schemas']['ProposalCommand'];

export type GenerationRecord = components['schemas']['GenerationRecord'];

export type PlaybookEntry = components['schemas']['PlaybookEntry'];

export type ArenaView = components['schemas']['ArenaView'];

export type ArenaControl = components['schemas']['ArenaControl'];

export type SubmitProposal = components['schemas']['SubmitProposal'];

export type ArenaCommand = components['schemas']['ArenaCommand-Input'];
export type ReflectCommand = components['schemas']['ReflectCommand-Input'];

export type ReviewStatus = components['schemas']['ReviewStatus'];

export type ReviewRecord = components['schemas']['ReviewRecord'];

export type MetaCaseCommand = components['schemas']['MetaCaseCommand'];

export type CalibrationView = components['schemas']['CalibrationView'];

export type ReviewCommand = components['schemas']['ReviewCommand-Input'];
export type HumanRevision = components['schemas']['HumanRevision-Input'];

export type DatasetStatus = components['schemas']['DatasetStatus'];
export type DataGrant = components['schemas']['DataGrant'];
export type DataGrantCommand = components['schemas']['DataGrantCommand-Input'];
export type DatasetBuild = components['schemas']['DatasetBuild-Input'];
export type DatasetSnapshot = components['schemas']['DatasetSnapshot'];
export type DatasetWithdrawal = components['schemas']['DatasetWithdrawal-Input'];
export type ExportCommand = components['schemas']['ExportCommand-Input'];
export type DatasetArtifact = components['schemas']['DatasetArtifact'];

export type TrainingStatus = components['schemas']['TrainingStatus'];
export type TrainingPlan = components['schemas']['TrainingPlan'];
export type TrainingPlanCommand = components['schemas']['TrainingPlanCommand-Input'];
export type TrainingJob = components['schemas']['TrainingJob'];
export type TrainingJobCommand = components['schemas']['TrainingJobCommand'];
export type TrainingControl = components['schemas']['TrainingControl'];
export type TrainingBundle = components['schemas']['TrainingBundle'];

export type DecisionEvaluation = components['schemas']['DecisionEvaluation'];
export type DecisionEvaluationCommand = components['schemas']['DecisionEvaluationCommand-Input'];
export type ShadowEvaluation = components['schemas']['ShadowEvaluation'];

export type ReleaseRecord = components['schemas']['ReleaseRecord'];
export type ReleaseStatus = components['schemas']['ReleaseStatus'];
export type ReleasePlanCommand = components['schemas']['ReleasePlanCommand-Input'];
export type ReleaseApproval = components['schemas']['ReleaseApproval'];
export type ReleaseControl = components['schemas']['ReleaseControl'];
export type ReleaseObservation = components['schemas']['ReleaseObservation'];
export type ReleaseValidationRun = components['schemas']['ReleaseValidationRun'];

export type Schedule = components['schemas']['Schedule'];
export type ScheduleCommand = components['schemas']['ScheduleCommand-Input'];
export type BackgroundJob = components['schemas']['BackgroundJob'];
export type OperationsStatus = components['schemas']['OperationsStatus'];
export type OperationsControl = components['schemas']['OperationsControl'];
export type TelemetrySample = components['schemas']['TelemetrySample'];
export type OperationsAlert = components['schemas']['OperationsAlert'];
export type BackupManifest = components['schemas']['BackupManifest'];
export type RestoreCommand = components['schemas']['RestoreCommand'];

export type WorkspaceConversation = components['schemas']['WorkspaceConversation'];
export type ConversationView = components['schemas']['ConversationView'];
export type ConversationTurn = components['schemas']['ConversationTurn'];
export type ConversationCreate = components['schemas']['ConversationCreate'];

export type LocalDirectories = components['schemas']['LocalDirectories'];
