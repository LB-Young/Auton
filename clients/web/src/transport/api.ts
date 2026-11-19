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
      training: {
        status: () => request('/training/status'),
        plans: (project) => request(`/training/plans?project_id=${encodeURIComponent(project)}`),
        plan: (command) => request('/training/plans', command),
        jobs: (project) => request(`/training/jobs?project_id=${encodeURIComponent(project)}`),
        create: (command) => request('/training/jobs', command),
        control: (id, command) =>
          request(`/training/jobs/${encodeURIComponent(id)}/commands`, command),
        bundles: (project) =>
          request(`/training/bundles?project_id=${encodeURIComponent(project)}`),
      },
      datasets: {
        status: () => request('/datasets/status'),
        grants: (project) => request(`/datasets/grants?project_id=${encodeURIComponent(project)}`),
        grant: (command) => request('/datasets/grants', command),
        list: (project) => request(`/datasets/snapshots?project_id=${encodeURIComponent(project)}`),
        build: (command) => request('/datasets/snapshots', command),
        withdraw: (command) => request('/datasets/withdrawals', command),
        export: (id, command) =>
          request(`/datasets/snapshots/${encodeURIComponent(id)}/exports`, command),
        download: async (id) => {
          const response = await fetch(base + `/datasets/artifacts/${encodeURIComponent(id)}`, {
            credentials: 'same-origin',
            cache: 'no-store',
          });
          if (!response.ok) {
            const error = (await response.json()) as ErrorBody;
            throw new ApiError(error.code, error.message);
          }
          const url = URL.createObjectURL(await response.blob());
          const link = document.createElement('a');
          link.href = url;
          link.download = `${id}.jsonl`;
          link.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        },
      },
      decisionReview: {
        status: () => request('/decision-review/status'),
        list: (project) =>
          request(`/decision-review/reviews?project_id=${encodeURIComponent(project)}`),
        get: (id) => request(`/decision-review/reviews/${encodeURIComponent(id)}`),
        review: (command) => request('/decision-review/jobs', command),
        revise: (id, command) =>
          request(`/decision-review/reviews/${encodeURIComponent(id)}/revisions`, command),
        calibrations: () => request('/decision-review/calibrations'),
        annotateMeta: (command) => request('/decision-review/meta', command),
      },
      evolution: {
        status: () => request('/evolution/status'),
        proposals: (project) =>
          request(`/evolution/proposals?project_id=${encodeURIComponent(project)}`),
        arenas: (project) => request(`/evolution/arenas?project_id=${encodeURIComponent(project)}`),
        generations: (project) =>
          request(`/evolution/generations?project_id=${encodeURIComponent(project)}`),
        playbook: (project) =>
          request(`/evolution/playbook?project_id=${encodeURIComponent(project)}`),
        diagnose: (command) => request('/evolution/diagnoses', command),
        propose: (command) => request('/evolution/proposals', command),
        reflect: (command) => request('/evolution/reflections', command),
        createArena: (command) => request('/evolution/arenas', command),
        arena: (id) => request(`/evolution/arenas/${encodeURIComponent(id)}`),
        control: (id, command) =>
          request(`/evolution/arenas/${encodeURIComponent(id)}/commands`, command),
        submit: (id, command) =>
          request(`/evolution/proposals/${encodeURIComponent(id)}/submit`, command),
      },
      delegation: {
        status: () => request('/delegation/status'),
        list: (project) => request(`/delegation?project_id=${encodeURIComponent(project)}`),
        get: (id) => request(`/delegation/${encodeURIComponent(id)}`),
        create: (command) => request('/delegation', command),
        command: (id, command) =>
          request(`/delegation/${encodeURIComponent(id)}/commands`, command),
        contrast: (id, command) =>
          request(`/delegation/${encodeURIComponent(id)}/contrast`, command),
      },
      assessment: {
        status: () => request('/assessment/status'),
        bank: () => request('/assessment/bank'),
        seed: (command) => request('/assessment/seed', command),
        importCases: (command) => request('/assessment/bank', command),
        windows: () => request('/assessment/windows'),
        openWindow: (command) => request('/assessment/windows', command),
        evaluate: (command) => request('/assessment/jobs', command),
        job: (id) => request(`/assessment/jobs/${encodeURIComponent(id)}`),
        reports: (project) =>
          request(`/assessment/reports?project_id=${encodeURIComponent(project)}`),
        aggregate: (project) =>
          request(`/assessment/aggregate?project_id=${encodeURIComponent(project)}`),
        compare: (command) => request('/assessment/compare', command),
        calibrations: () => request('/assessment/calibrations'),
        calibrate: (command) => request('/assessment/calibrations', command),
        batch: (command) => request('/assessment/batches', command),
      },
      runHistory: (project_id, after, search) =>
        request(
          `/agent/history?${new URLSearchParams({ project_id, after: String(after), search })}`,
        ),
      feedback: (id, command) => request(`/agent/runs/${encodeURIComponent(id)}/feedback`, command),
      artifactText: async (path) => {
        if (
          !/^\/api\/v1\/(agent\/runs\/[a-f0-9]+\/report|tools\/operations\/[a-zA-Z0-9_-]+\/artifact)$/.test(
            path,
          )
        )
          throw new ApiError('artifact_path', '无效产物引用');
        const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok) {
          const error = (await response.json().catch(() => ({}))) as Partial<ErrorBody>;
          throw new ApiError(error.code ?? 'artifact_unavailable', error.message ?? '产物不可读取');
        }
        if (Number(response.headers.get('Content-Length') ?? '0') > 1048576)
          throw new ApiError('artifact_too_large', '产物过大，请使用授权下载');
        const text = await response.text();
        if (text.length > 1048576)
          throw new ApiError('artifact_too_large', '产物过大，请使用授权下载');
        return text;
      },
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
