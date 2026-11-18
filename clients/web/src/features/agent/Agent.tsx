import { useEffect, useRef, useState, type ReactNode } from 'react';
import type {
  AgentRun,
  ModelInfo,
  Project,
  RunCommand,
  WorkspaceView,
} from '../../shared/contracts';
import { Markdown } from '../../shared/Markdown';
import type { AgentFeature } from './factory';

const statusLabels: Record<AgentRun['status'], string> = {
  queued: '已排队',
  running: '执行中',
  waiting_approval: '等待审批',
  blocked: '已阻塞',
  pausing: '等待安全暂停',
  paused: '已暂停',
  cancelling: '正在停止，等待在途操作确认',
  cancelled: '已停止',
  succeeded: '验收通过',
  failed: '验收未通过',
};
const terminal = new Set(['succeeded', 'failed', 'cancelled']);

export function Agent({
  feature,
  renderTrajectory,
}: {
  feature: AgentFeature;
  renderTrajectory?: (run: AgentRun, onRecovered: (run: AgentRun) => void) => ReactNode;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceView[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [project, setProject] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [model, setModel] = useState('');
  const [goal, setGoal] = useState('');
  const [boundaries, setBoundaries] = useState('');
  const [kind, setKind] = useState<'research' | 'file'>('research');
  const [path, setPath] = useState('notes.md');
  const [content, setContent] = useState('');
  const [isPublic, setPublic] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [revision, setRevision] = useState('');
  const scope = useRef(0);
  const running = run && !terminal.has(run.status);
  useEffect(() => {
    let live = true;
    Promise.all([feature.projects(), feature.workspaces(), feature.models()])
      .then(([p, w, m]) => {
        if (!live) return;
        setProjects(p);
        setWorkspaces(w);
        setModels(m);
        setProject(p[0]?.id ?? '');
        setWorkspace(w[0]?.id ?? '');
        setModel(m[0]?.id ?? '');
        setLoading(false);
      })
      .catch((e: Error) => {
        if (live) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      live = false;
      scope.current++;
    };
  }, [feature]);
  useEffect(() => {
    if (!project) return;
    const current = ++scope.current;
    setRun(null);
    setRuns([]);
    feature
      .list(project)
      .then((items) => {
        if (current === scope.current) setRuns(items);
      })
      .catch((e: Error) => {
        if (current === scope.current) setError(e.message);
      });
  }, [feature, project]);
  const identity = run?.id;
  useEffect(() => {
    if (!identity) return;
    let live = true;
    const refresh = async () => {
      try {
        const value = await feature.get(identity);
        if (live) {
          setRun((old) => (old?.id === identity && old.version <= value.version ? value : old));
          setRuns((old) =>
            old.map((r) => (r.id === value.id && r.version <= value.version ? value : r)),
          );
        }
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : '任务状态读取失败');
      }
    };
    const timer = window.setInterval(() => void refresh(), 900);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, [feature, identity]);
  async function act(action: () => Promise<AgentRun>) {
    const current = scope.current;
    setBusy(true);
    setError('');
    try {
      const value = await action();
      if (current === scope.current) {
        setRun((old) => (old?.id === value.id && old.version > value.version ? old : value));
        setRuns((old) => [value, ...old.filter((r) => r.id !== value.id)]);
      }
    } catch (e) {
      if (current === scope.current) setError(e instanceof Error ? e.message : '任务操作失败');
    } finally {
      setBusy(false);
    }
  }
  async function create() {
    await act(async () => {
      const sha =
        kind === 'file'
          ? Array.from(
              new Uint8Array(
                await crypto.subtle.digest('SHA-256', new TextEncoder().encode(content)),
              ),
            )
              .map((v) => v.toString(16).padStart(2, '0'))
              .join('')
          : null;
      return feature.create({
        request_id: crypto.randomUUID(),
        project_id: project,
        workspace_id: workspace,
        model_id: model,
        goal:
          kind === 'file' ? `${goal}\nWrite exactly this content to ${path}:\n${content}` : goal,
        boundaries: boundaries.split('\n').filter(Boolean),
        data_domain: isPublic ? 'public' : 'local-only',
        allowed_tools: kind === 'file' ? ['file.read', 'file.write'] : ['file.read'],
        acceptance: { kind, path: kind === 'file' ? path : null, sha256: sha, min_sources: 1 },
      });
    });
  }
  function command(action: RunCommand['action']) {
    if (!run) return;
    const selected = run;
    void act(() =>
      feature.command(selected.id, {
        request_id: crypto.randomUUID(),
        expected_goal_revision: selected.goal_revision,
        action,
        goal: action === 'revise' ? revision : null,
      }),
    );
  }
  return (
    <section className="module-page tool-page context-page agent-page">
      <p className="eyebrow">真实单 Agent · M09</p>
      <h1>任务</h1>
      <p className="module-description">
        从明确目标开始，通过模型和受控工具完成任务，由宿主核对交付。
      </p>
      <p className="module-note">
        Laya
        提供建议，执行模型由你选择。文件任务需逐项批准写入；调研仅使用已有项目资料和只读工具。主对话保留
        Demo。
      </p>
      {loading && <p role="status">正在加载任务连接…</p>}
      {error && (
        <p className="notice-banner" role="alert">
          {error}
        </p>
      )}
      {!loading && (!projects.length || !workspaces.length) && (
        <p>请先在资产页创建项目，并在工具页创建合适的工作区。</p>
      )}
      <article className="settings-card">
        <h2>创建任务</h2>
        <label className="judgment-label">
          项目
          <select
            aria-label="任务项目"
            value={project}
            disabled={busy}
            onChange={(e) => setProject(e.target.value)}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </label>
        <label className="judgment-label">
          工作区
          <select
            aria-label="任务工作区"
            value={workspace}
            disabled={busy}
            onChange={(e) => setWorkspace(e.target.value)}
          >
            {workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.title} {w.read_only ? '· 只读' : '· 可申请写入'}
              </option>
            ))}
          </select>
        </label>
        <label className="judgment-label">
          执行模型
          <select
            aria-label="任务模型"
            value={model}
            disabled={busy}
            onChange={(e) => setModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
              </option>
            ))}
          </select>
        </label>
        <label className="judgment-label">
          验收类型
          <select
            aria-label="任务验收类型"
            value={kind}
            onChange={(e) => setKind(e.target.value as 'research' | 'file')}
          >
            <option value="research">只读资料调研 · 引用检查</option>
            <option value="file">精确文件写入 · SHA256 检查</option>
          </select>
        </label>
        <label className="judgment-label">
          目标
          <textarea
            className="judgment-input"
            aria-label="真实任务目标"
            rows={3}
            maxLength={2000}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
        </label>
        <label className="judgment-label">
          必留边界（每行一条）
          <textarea
            className="judgment-input"
            aria-label="真实任务边界"
            rows={2}
            value={boundaries}
            onChange={(e) => setBoundaries(e.target.value)}
          />
        </label>
        {kind === 'file' && (
          <>
            <label className="judgment-label">
              目标路径
              <input
                aria-label="任务目标路径"
                value={path}
                maxLength={400}
                onChange={(e) => setPath(e.target.value)}
              />
            </label>
            <label className="judgment-label">
              期望的完整文件内容
              <textarea
                className="judgment-input"
                aria-label="任务期望内容"
                rows={4}
                value={content}
                maxLength={1000}
                onChange={(e) => setContent(e.target.value)}
              />
            </label>
          </>
        )}
        <label className="judgment-check">
          <input type="checkbox" checked={isPublic} onChange={(e) => setPublic(e.target.checked)} />
          确认任务、项目资料及工作区内容均可发送给所选远程模型
        </label>
        <button
          className="secondary-button"
          disabled={busy || loading || !project || !workspace || !model || !goal.trim()}
          onClick={() => void create()}
        >
          启动真实任务
        </button>
      </article>
      <article className="settings-card">
        <h2>项目任务</h2>
        {!runs.length && <p>当前没有任务</p>}
        {runs.map((r) => (
          <button
            key={r.id}
            className="secondary-button"
            disabled={busy}
            onClick={() => void act(() => feature.get(r.id))}
          >
            {r.command.goal.slice(0, 30)} · {statusLabels[r.status]}
          </button>
        ))}
      </article>
      {run && (
        <article className="settings-card agent-result" aria-label="真实任务执行记录">
          <h2>执行记录</h2>
          <p role="status">
            {statusLabels[run.status]} · {run.source === 'test' ? '测试替身' : '真实执行'}
          </p>
          <p className="module-note">{run.reason}</p>
          <dl>
            <div>
              <dt>目标修订 / 安全点</dt>
              <dd>
                {run.goal_revision} / {run.version}
              </dd>
            </div>
            <div>
              <dt>模型调用 / token</dt>
              <dd>
                {run.steps} / {run.tokens_used}
              </dd>
            </div>
            <div>
              <dt>估算费用</dt>
              <dd>${(run.cost_microusd / 1000000).toFixed(6)}</dd>
            </div>
          </dl>
          {running && (
            <div>
              <button
                className="secondary-button"
                disabled={busy || run.status === 'cancelling'}
                onClick={() => command('cancel')}
              >
                停止任务
              </button>
              <button
                className="secondary-button"
                disabled={busy || !['running', 'queued', 'waiting_approval'].includes(run.status)}
                onClick={() => command('pause')}
              >
                暂停任务
              </button>
              {['paused', 'blocked'].includes(run.status) && (
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => command('resume')}
                >
                  恢复任务
                </button>
              )}
            </div>
          )}
          {run.status === 'waiting_approval' && run.plans.at(-1) && (
            <div>
              <h3>待批准工具</h3>
              <p>{run.plans.at(-1)?.title}</p>
              <pre className="tool-output">{run.plans.at(-1)?.preview}</pre>
              <button
                className="secondary-button"
                disabled={busy}
                onClick={() => command('approve')}
              >
                批准本次任务操作
              </button>
            </div>
          )}
          {run.status === 'blocked' && run.phase === 'tool' && (
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() => command('reconcile')}
            >
              对账未知操作
            </button>
          )}
          {running && (
            <label className="judgment-label">
              修订目标
              <textarea
                className="judgment-input"
                aria-label="修订真实任务目标"
                rows={2}
                maxLength={4000}
                value={revision}
                onChange={(e) => setRevision(e.target.value)}
              />
              <button
                className="secondary-button"
                disabled={busy || !revision.trim() || run.status === 'cancelling'}
                onClick={() => command('revise')}
              >
                修订并安全暂停
              </button>
            </label>
          )}
          {run.pending_goal && <p>待安全应用的新目标：{run.pending_goal}</p>}
          {run.history
            .filter((m) => m.role !== 'tool')
            .map((m, i) => (
              <div className="agent-message" key={i}>
                <strong>{m.role === 'user' ? '你' : 'Agent'}</strong>
                <Markdown>{m.content ?? '请求受控工具'}</Markdown>
              </div>
            ))}
          {run.receipts.map((r) => (
            <details key={r.operation_id}>
              <summary>
                {r.tool} · {r.outcome} · {r.code}
              </summary>
              <pre className="tool-output">{r.output}</pre>
              <p>{r.evidence}</p>
              {r.artifact && (
                <a
                  href={`/api/v1/tools/operations/${encodeURIComponent(r.operation_id)}/artifact`}
                  download
                >
                  下载任务文件 {r.artifact.path}
                </a>
              )}
            </details>
          ))}
          {run.check && (
            <p className="notice-banner">
              宿主验收：{run.check.outcome} · {run.check.checker}
              。此检查验证摘要或引用结构，语义质量尚未独立评估。
            </p>
          )}
          {run.final_text && (
            <a href={`/api/v1/agent/runs/${encodeURIComponent(run.id)}/report`} download>
              下载任务报告
            </a>
          )}
          {renderTrajectory?.(run, (value) => {
            setRun(value);
            setRuns((old) => old.map((r) => (r.id === value.id ? value : r)));
          })}
          <details>
            <summary>判断、上下文与模型来源</summary>
            <pre className="tool-output">
              {JSON.stringify(
                {
                  runtime: run.runtime_revision,
                  judgment: run.judgments.map((j) => ({
                    source: j.source,
                    adopted: j.adopted,
                    raw_event: j.raw_event_id,
                  })),
                  executor_selection: run.executor_selection,
                  input_cutoff_unit: run.input_cutoff_unit,
                  contexts: run.context_ids,
                  models: run.model_results.map((m) => ({
                    model: m.reported_model,
                    fingerprint: m.system_fingerprint,
                    source: m.source,
                    usage: m.usage,
                  })),
                },
                null,
                2,
              )}
            </pre>
          </details>
        </article>
      )}
    </section>
  );
}
