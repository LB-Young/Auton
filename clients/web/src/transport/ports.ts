import type {
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
