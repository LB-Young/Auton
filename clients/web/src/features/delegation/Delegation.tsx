import { useEffect, useRef, useState } from 'react';
import type {
  DelegationCommand,
  DelegationCreate,
  DelegationStatus,
  DelegationView,
  ModelInfo,
  Project,
  SingleMultiContrast,
  WorkspaceView,
} from '../../shared/contracts';
import type { DelegationFeature } from './factory';

const labels: Record<string, string> = {
  draft: '待启动',
  running: '运行中',
  waiting_approval: '等待审批',
  integrating: '正在集成',
  integrated: '父目标验收通过',
  cancelling: '正在取消',
  cancelled: '已取消',
  blocked: '已阻塞',
  pending: '等待依赖',
  verified: '独立验收通过',
  succeeded: '子运行结束',
  dispatch_intent: '派发待确认',
};
const money = (n: number) => `$${(n / 1000000).toFixed(6)}`;

export function Delegation({ feature }: { feature: DelegationFeature }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceView[]>([]);
  const [status, setStatus] = useState<DelegationStatus | null>(null);
  const [parents, setParents] = useState<DelegationView[]>([]);
  const [parent, setParent] = useState<DelegationView | null>(null);
  const [json, setJson] = useState('');
  const [baseline, setBaseline] = useState('');
  const [contrast, setContrast] = useState<SingleMultiContrast | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  const actionRef = useRef<{ signature: string; command: DelegationCommand } | null>(null);
  useEffect(() => {
    mounted.current = true;
    Promise.all([feature.projects(), feature.models(), feature.workspaces(), feature.api.status()])
      .then(([p, m, w, s]) => {
        if (!mounted.current) return;
        setProjects(p);
        setModels(m);
        setWorkspaces(w);
        setStatus(s);
        setProject(p[0]?.id ?? '');
        setLoading(false);
      })
      .catch((e: Error) => {
        if (mounted.current) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      mounted.current = false;
      generation.current++;
    };
  }, [feature]);
  useEffect(() => {
    const current = ++generation.current;
    setParent(null);
    setParents([]);
    setContrast(null);
    setError('');
    if (project)
      feature.api
        .list(project)
        .then((p) => {
          if (current === generation.current) {
            setParents(p);
            setParent(p.at(-1) ?? null);
          }
        })
        .catch((e: Error) => {
          if (current === generation.current) setError(e.message);
        });
    return () => {
      generation.current++;
    };
  }, [feature, project]);
  useEffect(() => {
    if (!parent || busy || !['running', 'integrating', 'cancelling'].includes(parent.status))
      return;
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const current = generation.current;
    async function poll() {
      try {
        const value = await feature.api.get(parent!.id);
        if (!live || current !== generation.current) return;
        setParent((old) => (old?.id === value.id && value.version >= old.version ? value : old));
        setParents((old) => old.map((p) => (p.id === value.id ? value : p)));
        timer = setTimeout(() => void poll(), 700);
      } catch (e) {
        if (live && current === generation.current)
          setError(e instanceof Error ? e.message : '读取失败');
      }
    }
    timer = setTimeout(() => void poll(), 250);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [feature, parent?.id, parent?.status, busy]);
  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : '操作失败');
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  function adopt(value: DelegationView) {
    if (!mounted.current) return;
    setParent(value);
    setParents((old) =>
      old.some((p) => p.id === value.id)
        ? old.map((p) => (p.id === value.id ? value : p))
        : [...old, value],
    );
  }
  async function control(action: DelegationCommand['action'], child: string | null = null) {
    if (!parent) return;
    const signature = JSON.stringify([parent.id, parent.version, action, child]);
    if (actionRef.current?.signature !== signature)
      actionRef.current = {
        signature,
        command: {
          request_id: crypto.randomUUID(),
          expected_version: parent.version,
          action,
          child_id: child,
        },
      };
    try {
      adopt(await feature.api.command(parent.id, actionRef.current.command));
      actionRef.current = null;
    } catch (e) {
      adopt(await feature.api.get(parent.id));
      throw e;
    }
  }
  function example() {
    if (!status || !project || !models.length || !workspaces.length) return;
    const limits = status.host_limits;
    const child = {
      max_steps: Math.floor(limits.max_steps / 2),
      max_tokens: Math.floor(limits.max_tokens / 2),
      max_cost_microusd: Math.floor(limits.max_cost_microusd / 2),
      max_tool_calls: Math.floor((limits.max_tool_calls - 1) / 2),
      max_output_tokens: limits.max_output_tokens,
    };
    setJson(
      JSON.stringify(
        {
          request_id: crypto.randomUUID(),
          project_id: project,
          workspace_id: workspaces.find((w) => !w.read_only)?.id ?? '',
          goal: 'Write hello followed by a newline twice to delivery.md.',
          public: false,
          limits,
          children: ['alpha', 'beta'].map((id) => ({
            id,
            role: 'worker',
            goal: 'Write hello followed by a newline exactly to notes.md.',
            model_id: models[0].id,
            depends_on: [],
            limits: child,
            allowed_tools: ['file.write'],
            acceptance: {
              kind: 'file',
              path: 'notes.md',
              sha256: '5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03',
            },
          })),
          merge_order: ['alpha', 'beta'],
          separator: '',
          acceptance: {
            kind: 'file',
            path: 'delivery.md',
            sha256: 'cba5243834a58801d5f3460c1d21fe28c33b1e1c1bb8ce7513e1948eed3a19e4',
          },
        },
        null,
        2,
      ),
    );
  }
  const disabled = busy || loading;
  return (
    <section className="module-page tool-page delegation-page">
      <p className="eyebrow">受限委派 · M14</p>
      <h1>多 Agent</h1>
      <p className="module-description">
        定义父目标与任务依赖，让各个工作者独立交付，再核验并批准最终合并。
      </p>
      <p className="module-note">
        首期由你明确子任务与验收条件。子任务使用私有工作区，不能自行审批；预算在启动前分配，更多调用不代表更好。
      </p>
      {loading && <p role="status">正在读取委派配置…</p>}
      {busy && <p role="status">正在提交操作…</p>}
      {error && (
        <p className="notice-banner" role="alert">
          {error}
        </p>
      )}
      <article className="settings-card">
        <h2>父任务</h2>
        <label className="judgment-label">
          项目
          <select
            aria-label="委派项目"
            disabled={disabled}
            value={project}
            onChange={(e) => setProject(e.target.value)}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </label>
        {!projects.length && !loading && <p>请先在任务页创建项目与可写工作区。</p>}
        {!parents.length && project && <p>当前项目没有委派任务。</p>}
        <select
          aria-label="选择父任务"
          value={parent?.id ?? ''}
          disabled={disabled}
          onChange={(e) => {
            setContrast(null);
            setParent(parents.find((p) => p.id === e.target.value) ?? null);
          }}
        >
          <option value="">选择父任务</option>
          {parents.map((p) => (
            <option key={p.id} value={p.id}>
              {p.command.goal.slice(0, 70)} · {labels[p.status]}
            </option>
          ))}
        </select>
        <button
          className="secondary-button"
          disabled={disabled || !parent}
          onClick={() => void perform(async () => adopt(await feature.api.get(parent!.id)))}
        >
          刷新父任务
        </button>
      </article>
      <details className="settings-card">
        <summary>新建任务契约</summary>
        {status && (
          <p>
            最多 {status.max_children} 个子任务，同时运行 {status.max_parallel} 个；单个子任务最长{' '}
            {status.child_timeout_seconds} 秒（含等待审批）。
          </p>
        )}
        <p>
          JSON
          明确目标、边界、固定资料快照、依赖、模型、每个子任务的预算与独立文件摘要。远程任务需显式
          public=true，执行和判断可能产生费用。
        </p>
        <button
          className="secondary-button"
          disabled={disabled || !project || !models.length || !workspaces.length}
          onClick={example}
        >
          填入公开合成示例（不自动运行）
        </button>
        <label className="judgment-label">
          任务契约 JSON
          <textarea
            aria-label="委派契约 JSON"
            rows={16}
            value={json}
            disabled={disabled}
            onChange={(e) => setJson(e.target.value)}
          />
        </label>
        <button
          className="secondary-button"
          disabled={disabled || !json.trim()}
          onClick={() =>
            void perform(async () => {
              const command: unknown = JSON.parse(json);
              if (!command || typeof command !== 'object' || Array.isArray(command))
                throw new Error('请输入 JSON 对象');
              if ((command as DelegationCreate).project_id !== project)
                throw new Error('契约所属项目与当前页面不同，请先切换到对应项目');
              const value = await feature.api.create(command as DelegationCreate);
              adopt(value);
            })
          }
        >
          创建父任务
        </button>
      </details>
      {parent && (
        <>
          <article className="settings-card" aria-label="父任务状态">
            <h2>{labels[parent.status]}</h2>
            <p>{parent.command.goal}</p>
            <p>{parent.reason}</p>
            <p>
              v{parent.version} · {parent.source === 'test' ? '测试夹具' : '真实运行'} · 固定资料{' '}
              <code>{parent.input_snapshot_id}</code>
            </p>
            <p>
              总执行 tokens {parent.total_tokens} / {parent.command.limits.max_tokens} · 已知费用{' '}
              {money(parent.total_cost_microusd)} / {money(parent.command.limits.max_cost_microusd)}
            </p>
            <p>
              工具调用 {parent.total_tool_calls} / {parent.command.limits.max_tool_calls} ·
              未知模型调用 {parent.unknown_calls} · 未知工具 {parent.unknown_tools}
            </p>
            <p>
              共同影响组：{parent.interaction_group.join(' + ')}
              。仅记录联合贡献，不对每次判断机械奖惩。
            </p>
            {['draft', 'blocked'].includes(parent.status) && (
              <button
                className="secondary-button"
                disabled={disabled}
                onClick={() =>
                  void perform(() => control(parent.status === 'draft' ? 'start' : 'resume'))
                }
              >
                {parent.status === 'draft' ? '启动委派' : '显式恢复委派'}
              </button>
            )}
            {!['integrated', 'cancelled'].includes(parent.status) && (
              <button
                className="secondary-button"
                disabled={disabled}
                onClick={() => void perform(() => control('cancel'))}
              >
                取消父任务与子任务
              </button>
            )}
          </article>
          <article className="settings-card" aria-label="任务 DAG">
            <h2>依赖与子任务</h2>
            <ol className="delegation-dag">
              {parent.children.map((c) => {
                const spec = parent.command.children.find((s) => s.id === c.id)!;
                return (
                  <li key={c.id} className="delegation-node">
                    <h3>
                      {c.id} · {labels[c.status] ?? c.status}
                    </h3>
                    <p>
                      {spec.depends_on.length
                        ? `${spec.depends_on.join(' + ')} → ${c.id}`
                        : `父目标 → ${c.id}`}
                    </p>
                    <p>{spec.goal}</p>
                    <p>
                      {spec.model_id} · {c.reason}
                    </p>
                    <p>
                      预算：{spec.limits.max_tokens} tokens / {money(spec.limits.max_cost_microusd)}{' '}
                      / {spec.limits.max_tool_calls} 次工具
                    </p>
                    <p>
                      已用：{c.tokens} tokens / {money(c.cost_microusd)} · 未知调用{' '}
                      {c.unknown_calls} · 未知工具 {c.unknown_tools}
                    </p>
                    {c.command && (
                      <p>
                        私有工作区：<code>{c.command.workspace_id}</code>
                      </p>
                    )}
                    {c.run_id && (
                      <a
                        href={`?view=agent&project=${encodeURIComponent(project)}&run=${c.run_id}`}
                      >
                        查看 {c.id} 的运行与审批差异
                      </a>
                    )}
                    {c.pending_preview && (
                      <pre aria-label={`${c.id} 待审批差异`}>{c.pending_preview}</pre>
                    )}
                    {c.status === 'waiting_approval' && parent.status === 'running' && (
                      <button
                        className="secondary-button"
                        disabled={disabled}
                        onClick={() => void perform(() => control('approve_child', c.id))}
                      >
                        批准子任务 {c.id} 本次操作
                      </button>
                    )}
                    {c.report_id && (
                      <p>
                        独立报告：<code>{c.report_id}</code>
                      </p>
                    )}
                  </li>
                );
              })}
            </ol>
          </article>
          {parent.integration && (
            <article className="settings-card" aria-label="集成差异">
              <h2>父目标集成</h2>
              <p>
                顺序：{parent.command.merge_order.join(' → ')} · 目标文件：
                {parent.command.acceptance.path}
              </p>
              <pre>{parent.integration.preview}</pre>
              {parent.status === 'waiting_approval' && (
                <button
                  className="secondary-button"
                  disabled={disabled}
                  onClick={() => void perform(() => control('approve_integration'))}
                >
                  批准最终合并
                </button>
              )}
              {parent.integration_receipt && (
                <p>
                  集成凭据：{parent.integration_receipt.outcome} · {parent.integration_receipt.code}
                </p>
              )}
              {parent.integration_receipt?.outcome === 'succeeded' && (
                <a
                  href={`/api/v1/tools/operations/${parent.integration_receipt.operation_id}/artifact`}
                >
                  下载父任务交付
                </a>
              )}
            </article>
          )}
          <article className="settings-card">
            <h2>单、多 Agent 对照</h2>
            <p>
              输入同一父目标、验收、资料快照及总预算的单 Agent 运行
              ID。只展示这一次成对工作流的质量与成本，不据此宣称整体提升。
            </p>
            <label className="judgment-label">
              单 Agent 基线运行 ID
              <input
                aria-label="单 Agent 基线运行 ID"
                value={baseline}
                disabled={disabled}
                onChange={(e) => {
                  setBaseline(e.target.value);
                  setContrast(null);
                }}
              />
            </label>
            <button
              className="secondary-button"
              disabled={disabled || !/^[a-f0-9]{64}$/.test(baseline)}
              onClick={() =>
                void perform(async () => {
                  const run = await feature.baseline(baseline);
                  setContrast(
                    await feature.api.contrast(parent.id, {
                      request_id: crypto.randomUUID(),
                      baseline_run_id: baseline,
                      expected_version: run.version,
                    }),
                  );
                })
              }
            >
              比较单多 Agent
            </button>
            {contrast && (
              <div role="status">
                <p>
                  {contrast.comparable ? '同条件单次对照' : '条件不可比'} ·{' '}
                  {contrast.source === 'test' ? '测试夹具' : '真实运行'}
                </p>
                <p>{contrast.reasons.join(' / ')}</p>
                <p>
                  单 Agent：{contrast.baseline_outcome}，{contrast.baseline_calls} 次模型调用，
                  {contrast.baseline_tokens} tokens，{money(contrast.baseline_cost_microusd)}
                </p>
                <p>
                  多 Agent：{contrast.multi_outcome}，{contrast.worker_calls} 次模型调用，
                  {contrast.worker_tokens} tokens，{money(contrast.worker_cost_microusd)}
                </p>
                <p>费用差值：{money(contrast.cost_delta_microusd)} · 整体改进尚未建立。</p>
              </div>
            )}
          </article>
        </>
      )}
    </section>
  );
}
