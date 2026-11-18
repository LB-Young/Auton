import type {
  Trajectory,
  AgentRun,
  ContextSnapshot,
  ActionRequest,
  PolicyDecision,
  JudgmentInfo,
  JudgmentResult,
  ToolDescriptor,
  ToolPlan,
  ToolApproval,
  ToolReceipt,
  WorkspaceView,
  Project,
  AssetRevision,
  Snapshot,
  VersionInfo,
  ModelInfo,
  ModelResult,
  Bootstrap,
  Session,
  ErrorBody,
  CreateSession,
  SendMessage,
  StopRun,
} from '../shared/contracts';
import type { ApiClient } from './ports';

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export class ApiClientFactory {
  create(base = '/api/v1'): ApiClient {
    async function request<T>(path: string, body?: object): Promise<T> {
      const response = await fetch(base + path, {
        method: body === undefined ? 'GET' : 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: body ? { 'Content-Type': 'application/json', 'X-Auton-Client': 'web' } : {},
        body: body === undefined ? undefined : JSON.stringify(body),
      }).catch(() => {
        throw new ApiError('network_error', '连接中断，请检查后端并重试');
      });
      if (!response.ok) {
        const error = (await response.json().catch(() => ({}))) as Partial<ErrorBody>;
        throw new ApiError(error.code ?? 'request_failed', error.message ?? '请求失败，请稍后重试');
      }
      return (await response.json()) as T;
    }
    return {
      adoptLegacy: (project_id) => request('/identity/adopt-legacy', { project_id }),
      runSnapshot: (id) => request(`/agent/runs/${encodeURIComponent(id)}/snapshot`),
      resetIdentity: () => request('/identity/reset', { request_id: crypto.randomUUID() }),
      prepareUpload: (command) => request('/uploads', command),
      uploadContent: async (id, bytes) => {
        const response = await fetch(base + `/uploads/${encodeURIComponent(id)}/content`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/octet-stream', 'X-Auton-Client': 'web' },
          body: bytes,
        });
        if (!response.ok) {
          const error = (await response.json().catch(() => ({}))) as Partial<ErrorBody>;
          throw new ApiError(error.code ?? 'upload_failed', error.message ?? '上传失败');
        }
        return response.json();
      },
      trajectory: (project, run) =>
        request<Trajectory>(
          `/projects/${encodeURIComponent(project)}/runs/${encodeURIComponent(run)}/trajectory`,
        ),
      recoverRun: (project, run, command) =>
        request<AgentRun>(
          `/projects/${encodeURIComponent(project)}/runs/${encodeURIComponent(run)}/recover`,
          command,
        ),
      createRun: (command) => request<AgentRun>('/agent/runs', command),
      agentRun: (id) => request<AgentRun>(`/agent/runs/${encodeURIComponent(id)}`),
      agentRuns: (project) =>
        request<AgentRun[]>(`/agent/runs?project_id=${encodeURIComponent(project)}`),
      agentCommand: (id, command) =>
        request<AgentRun>(`/agent/runs/${encodeURIComponent(id)}/commands`, command),
      prepareContext: (project, command) =>
        request<ContextSnapshot>(`/projects/${encodeURIComponent(project)}/context`, command),
      contextSnapshot: (project, id) =>
        request<ContextSnapshot>(
          `/projects/${encodeURIComponent(project)}/context/${encodeURIComponent(id)}`,
        ),
      judgment: () => request<JudgmentInfo>('/judgment'),
      previewJudgment: (state, isPublic, request_id) =>
        request<JudgmentResult>('/judgment/preview', { state, public: isPublic, request_id }),
      tools: () => request<ToolDescriptor[]>('/tools'),
      toolWorkspaces: () => request<WorkspaceView[]>('/tools/workspaces'),
      createToolWorkspace: (id, read_only) =>
        request<WorkspaceView>('/tools/workspaces', { id, title: '工具验证', read_only }),
      prepareTool: (command) => request<ToolPlan>('/tools/operations', command),
      approveTool: (id) =>
        request<ToolApproval>(`/tools/operations/${encodeURIComponent(id)}/approve`, {}),
      executeTool: (id, approval_id) =>
        request<ToolReceipt>(`/tools/operations/${encodeURIComponent(id)}/execute`, {
          approval_id,
        }),
      reconcileTool: (id) =>
        request<ToolReceipt>(`/tools/operations/${encodeURIComponent(id)}/reconcile`, {}),
      projects: () => request<Project[]>('/projects'),
      createProject: (project) => request<AssetRevision>('/projects', project),
      assets: (project) =>
        request<AssetRevision>(`/projects/${encodeURIComponent(project)}/assets`),
      proposeAsset: (project, asset, expected) =>
        request<AssetRevision>(`/projects/${encodeURIComponent(project)}/candidates`, {
          asset,
          expected,
        }),
      changeAsset: (project, id, action, expected, revision) =>
        request<AssetRevision>(
          `/projects/${encodeURIComponent(project)}/assets/${encodeURIComponent(id)}/${action}`,
          action === 'promote'
            ? { expected, candidates_revision: revision }
            : { expected, revision },
        ),
      assetHistory: (project, id) =>
        request<VersionInfo[]>(
          `/projects/${encodeURIComponent(project)}/assets/${encodeURIComponent(id)}/history`,
        ),
      assetDiff: (project, id, revision) =>
        request<string>(
          `/projects/${encodeURIComponent(project)}/assets/${encodeURIComponent(id)}/diff?revision=${encodeURIComponent(revision)}`,
        ),
      resolveAssets: (project) =>
        request<Snapshot>(`/projects/${encodeURIComponent(project)}/snapshots`, {}),
      models: () => request<ModelInfo[]>('/models'),
      probeModel: (id, request_id) =>
        request<ModelResult>(`/models/${encodeURIComponent(id)}/probe`, { request_id }),
      bootstrap: () => request<Bootstrap>('/bootstrap'),
      preview: (action: ActionRequest) => request<PolicyDecision>('/policy/preview', action),
      sessions: () => request<Session[]>('/sessions'),
      create: (request_id) => request<Session>('/sessions', { request_id } satisfies CreateSession),
      send: (id, content, request_id) =>
        request<Session>(`/sessions/${encodeURIComponent(id)}/messages`, {
          content,
          request_id,
        } satisfies SendMessage),
      stop: (id, run_id, request_id) =>
        request<Session>(`/sessions/${encodeURIComponent(id)}/stop`, {
          run_id,
          request_id,
        } satisfies StopRun),
    };
  }
}
