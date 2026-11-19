import type {
  Trajectory,
  RecoveryCommand,
  AgentRun,
  CreateRun,
  RunCommand,
  ContextSnapshot,
  ContextPreviewCommand,
  JudgmentInfo,
  JudgmentResult,
  ToolDescriptor,
  ToolPrepareCommand,
  ToolPlan,
  ToolApproval,
  ToolReceipt,
  WorkspaceView,
  Asset,
  Project,
  AssetRevision,
  Snapshot,
  VersionInfo,
  ModelInfo,
  ModelResult,
  Bootstrap,
  Session,
  SessionEvent,
  ActionRequest,
  PolicyDecision,
} from '../shared/contracts';

export interface ApiClient {
  assessment: AssessmentApi;
  decisionReview: DecisionReviewApi;
  evolution: EvolutionApi;
  delegation: DelegationApi;
  runHistory(
    project: string,
    after: number,
    search: string,
  ): Promise<import('../shared/contracts').RunPage>;
  feedback(
    id: string,
    command: import('../shared/contracts').FeedbackCommand,
  ): Promise<import('../shared/contracts').FeedbackReceipt>;
  artifactText(url: string): Promise<string>;
  adoptLegacy(project: string): Promise<unknown>;
  runSnapshot(id: string): Promise<import('../shared/contracts').RunSnapshot>;
  resetIdentity(): Promise<import('../shared/api.generated').components['schemas']['IdentityInfo']>;
  prepareUpload(
    command: import('../shared/contracts').UploadCommand,
  ): Promise<import('../shared/contracts').UploadIntent>;
  uploadContent(
    id: string,
    bytes: Uint8Array<ArrayBuffer>,
  ): Promise<import('../shared/contracts').UploadReceipt>;
  trajectory(project: string, run: string): Promise<Trajectory>;
  recoverRun(project: string, run: string, command: RecoveryCommand): Promise<AgentRun>;
  createRun(command: CreateRun): Promise<AgentRun>;
  agentRun(id: string): Promise<AgentRun>;
  agentRuns(project: string): Promise<AgentRun[]>;
  agentCommand(id: string, command: RunCommand): Promise<AgentRun>;
  prepareContext(project: string, command: ContextPreviewCommand): Promise<ContextSnapshot>;
  contextSnapshot(project: string, id: string): Promise<ContextSnapshot>;
  judgment(): Promise<JudgmentInfo>;
  previewJudgment(state: string, isPublic: boolean, requestId: string): Promise<JudgmentResult>;
  tools(): Promise<ToolDescriptor[]>;
  toolWorkspaces(): Promise<WorkspaceView[]>;
  createToolWorkspace(id: string, readOnly: boolean): Promise<WorkspaceView>;
  prepareTool(command: ToolPrepareCommand): Promise<ToolPlan>;
  approveTool(id: string): Promise<ToolApproval>;
  executeTool(id: string, approvalId: string | null): Promise<ToolReceipt>;
  reconcileTool(id: string): Promise<ToolReceipt>;
  projects(): Promise<Project[]>;
  createProject(project: Project): Promise<AssetRevision>;
  assets(project: string): Promise<AssetRevision>;
  proposeAsset(project: string, asset: Asset, expected: string | null): Promise<AssetRevision>;
  changeAsset(
    project: string,
    id: string,
    action: 'promote' | 'revoke' | 'rollback',
    expected: string,
    revision: string | null,
  ): Promise<AssetRevision>;
  assetHistory(project: string, id: string): Promise<VersionInfo[]>;
  assetDiff(project: string, id: string, revision: string): Promise<string>;
  resolveAssets(project: string): Promise<Snapshot>;
  models(): Promise<ModelInfo[]>;
  probeModel(id: string, requestId: string): Promise<ModelResult>;
  bootstrap(): Promise<Bootstrap>;
  preview(action: ActionRequest): Promise<PolicyDecision>;
  sessions(): Promise<Session[]>;
  create(requestId: string): Promise<Session>;
  send(id: string, content: string, requestId: string): Promise<Session>;
  stop(id: string, runId: string, requestId: string): Promise<Session>;
}

export interface EventStream {
  connect(
    sessionId: string,
    onSnapshot: (event: SessionEvent) => void,
    onConnection: (connected: boolean) => void,
  ): () => void;
}

export interface RunEventStream {
  connect(
    runId: string,
    onFrame: (frame: import('../shared/contracts').RunFrame) => void,
    onConnection: (connected: boolean) => void,
  ): () => void;
}

export interface AssessmentApi {
  status(): Promise<import('../shared/contracts').AssessmentStatus>;
  bank(): Promise<import('../shared/contracts').CaseBank>;
  seed(
    command: import('../shared/contracts').SeedCommand,
  ): Promise<import('../shared/contracts').CaseBank>;
  importCases(
    command: import('../shared/contracts').ImportCases,
  ): Promise<import('../shared/contracts').CaseBank>;
  windows(): Promise<import('../shared/contracts').WindowView[]>;
  openWindow(
    command: import('../shared/contracts').BlindWindowCommand,
  ): Promise<import('../shared/contracts').BlindWindow>;
  evaluate(
    command: import('../shared/contracts').EvaluateCommand,
  ): Promise<import('../shared/contracts').EvalJob>;
  job(id: string): Promise<import('../shared/contracts').EvalJob>;
  reports(project: string): Promise<import('../shared/contracts').EvalReport[]>;
  aggregate(project: string): Promise<import('../shared/contracts').Aggregate>;
  compare(
    command: import('../shared/contracts').CompareCommand,
  ): Promise<import('../shared/contracts').Comparison>;
  calibrations(): Promise<import('../shared/contracts').CalibrationReport[]>;
  calibrate(
    command: import('../shared/contracts').CalibrationCommand,
  ): Promise<import('../shared/contracts').CalibrationReport>;
  batch(
    command: import('../shared/contracts').BatchEvaluation,
  ): Promise<import('../shared/contracts').BatchResult>;
}

export interface DelegationApi {
  status(): Promise<import('../shared/contracts').DelegationStatus>;
  list(project: string): Promise<import('../shared/contracts').DelegationView[]>;
  get(id: string): Promise<import('../shared/contracts').DelegationView>;
  create(
    command: import('../shared/contracts').DelegationCreate,
  ): Promise<import('../shared/contracts').DelegationView>;
  command(
    id: string,
    command: import('../shared/contracts').DelegationCommand,
  ): Promise<import('../shared/contracts').DelegationView>;
  contrast(
    id: string,
    command: import('../shared/contracts').ContrastCommand,
  ): Promise<import('../shared/contracts').SingleMultiContrast>;
}

export interface EvolutionApi {
  status(): Promise<import('../shared/contracts').EvolutionStatus>;
  proposals(project: string): Promise<import('../shared/contracts').Proposal[]>;
  arenas(project: string): Promise<import('../shared/contracts').ArenaView[]>;
  generations(project: string): Promise<import('../shared/contracts').GenerationRecord[]>;
  playbook(project: string): Promise<import('../shared/contracts').PlaybookEntry[]>;
  diagnose(
    command: import('../shared/contracts').DiagnoseCommand,
  ): Promise<import('../shared/contracts').Diagnosis>;
  propose(
    command: import('../shared/contracts').ProposalCommand,
  ): Promise<import('../shared/contracts').Proposal>;
  reflect(
    command: import('../shared/contracts').ReflectCommand,
  ): Promise<import('../shared/contracts').Proposal>;
  createArena(
    command: import('../shared/contracts').ArenaCommand,
  ): Promise<import('../shared/contracts').ArenaView>;
  arena(id: string): Promise<import('../shared/contracts').ArenaView>;
  control(
    id: string,
    command: import('../shared/contracts').ArenaControl,
  ): Promise<import('../shared/contracts').ArenaView>;
  submit(
    id: string,
    command: import('../shared/contracts').SubmitProposal,
  ): Promise<import('../shared/contracts').Proposal>;
}

export interface DecisionReviewApi {
  status(): Promise<import('../shared/contracts').ReviewStatus>;
  list(project: string): Promise<import('../shared/contracts').ReviewRecord[]>;
  get(id: string): Promise<import('../shared/contracts').ReviewRecord>;
  review(
    command: import('../shared/contracts').ReviewCommand,
  ): Promise<import('../shared/contracts').ReviewRecord>;
  revise(
    id: string,
    command: import('../shared/contracts').HumanRevision,
  ): Promise<import('../shared/contracts').ReviewRecord>;
  calibrations(): Promise<import('../shared/contracts').CalibrationView[]>;
  annotateMeta(
    command: import('../shared/contracts').MetaCaseCommand,
  ): Promise<import('../shared/contracts').CalibrationView>;
}
