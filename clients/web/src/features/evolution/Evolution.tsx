import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  ArenaCommand,
  ArenaControl,
  ArenaView,
  DiagnoseCommand,
  EvolutionStatus,
  GenerationRecord,
  PlaybookEntry,
  Project,
  Proposal,
  ProposalCommand,
  ReflectCommand,
} from '../../shared/contracts';
import type { EvolutionFeature } from './factory';

type Operation = 'diagnose' | 'propose' | 'reflect' | 'arena';
const labels = {
  diagnose: '诊断证据',
  propose: '提出局部补丁',
  reflect: '生成一次反思候选',
  arena: '冻结隔离评测',
};
const money = (n: number | null) => (n === null ? '未知' : `$${(n / 1000000).toFixed(6)}`);

export function Evolution({ feature }: { feature: EvolutionFeature }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [arenas, setArenas] = useState<ArenaView[]>([]);
  const [playbook, setPlaybook] = useState<PlaybookEntry[]>([]);
  const [generations, setGenerations] = useState<GenerationRecord[]>([]);
  const [status, setStatus] = useState<EvolutionStatus | null>(null);
  const [proposalId, setProposalId] = useState('');
  const [arenaId, setArenaId] = useState('');
  const [operation, setOperation] = useState<Operation>('diagnose');
  const [json, setJson] = useState('');
  const [result, setResult] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const epoch = useRef(0);
  const pending = useRef<{ signature: string; id: string } | null>(null);
  const proposal = proposals.find((p) => p.id === proposalId);
  const arena = arenas.find((a) => a.id === arenaId);
  useEffect(() => {
    let live = true;
    Promise.all([feature.projects(), feature.api.status()])
      .then(([p, s]) => {
        if (live) {
          setProjects(p);
          setProject(p[0]?.id ?? '');
          setStatus(s);
          setLoading(false);
        }
      })
      .catch((e: Error) => {
        if (live) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      live = false;
      epoch.current++;
    };
  }, [feature]);
  const refresh = useCallback(async () => {
    if (!project) return;
    const generation = epoch.current;
    const [p, a, b, g] = await Promise.all([
      feature.api.proposals(project),
      feature.api.arenas(project),
      feature.api.playbook(project),
      feature.api.generations(project),
    ]);
    if (generation !== epoch.current) return;
    setProposals(p);
    setArenas(a);
    setPlaybook(b);
    setGenerations(g);
    setProposalId((old) => (p.some((v) => v.id === old) ? old : (p.at(-1)?.id ?? '')));
    setArenaId((old) => (a.some((v) => v.id === old) ? old : (a.at(-1)?.id ?? '')));
  }, [feature, project]);
  useEffect(() => {
    epoch.current++;
    setProposals([]);
    setArenas([]);
    setPlaybook([]);
    setGenerations([]);
    setJson('');
    setResult('');
    setError('');
    setReviewed(false);
    pending.current = null;
    const generation = epoch.current;
    refresh().catch((e: Error) => {
      if (generation === epoch.current) setError(e.message);
    });
  }, [refresh]);
  useEffect(() => {
    if (busy || !arenas.some((a) => ['running', 'cancelling'].includes(a.status))) return;
    const generation = epoch.current;
    const timer = setTimeout(() => {
      refresh().catch((e: Error) => {
        if (generation === epoch.current) setError(e.message);
      });
    }, 1000);
    return () => clearTimeout(timer);
  }, [arenas, busy, refresh]);
  async function run(action: () => Promise<unknown>) {
    const generation = epoch.current;
    setBusy(true);
    setError('');
    try {
      const value = await action();
      if (generation === epoch.current) {
        setResult(JSON.stringify(value, null, 2));
        pending.current = null;
        await refresh();
      }
    } catch (e) {
      if (generation === epoch.current) setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function example() {
    const generation = epoch.current;
    const [assets, snapshot, reports, bank, models] = await Promise.all([
      feature.assets(project),
      feature.snapshot(project),
      feature.reports(project),
      feature.bank(),
      feature.models(),
    ]);
    const target = assets.assets.find(
      (r) => r.status === 'active' && r.asset.kind === 'skill',
    )?.asset;
    const report = reports.find((r) => r.split === 'train' && r.current_evidence_valid);
    const id = crypto.randomUUID();
    let command: unknown;
    if (operation === 'diagnose')
      command = {
        request_id: id,
        project_id: project,
        asset_id: target?.id ?? '选择已启用的 Skill',
        report_ids: report ? [report.id] : [],
      };
    else if (operation === 'arena')
      command = {
        request_id: id,
        proposal_id: proposal?.id ?? '',
        expected_proposal_version: proposal?.version ?? 0,
        bank_revision: bank.revision,
        train_cases: bank.cases
          .filter((c) => c.split === 'train' && c.kind === 'file')
          .slice(0, 1)
          .map((c) => c.id),
        development_cases: bank.cases
          .filter((c) => c.split === 'development' && c.kind === 'file')
          .slice(0, 5)
          .map((c) => c.id),
        repeats: 3,
        model_id: models.find((m) => m.capabilities.includes('tools'))?.id ?? '',
        limits: { max_steps: 3, max_tokens: 8000, max_cost_microusd: 4000, max_tool_calls: 1 },
        checkpoints: [
          { name: 'old-digest', tool: 'file_write', require_absent_or_null_old_digest: true },
        ],
        public: false,
      };
    else {
      const digest = target
        ? Array.from(
            new Uint8Array(
              await crypto.subtle.digest('SHA-256', new TextEncoder().encode(target.content)),
            ),
          )
            .map((b) => b.toString(16).padStart(2, '0'))
            .join('')
        : '';
      command = {
        request_id: id,
        project_id: project,
        diagnosis_id: proposal?.command.diagnosis_id ?? '先诊断，填入返回的 id',
        base_snapshot_id: snapshot.id,
        asset_id: target?.id ?? '',
        expected_content_sha256: digest,
        direction: '只改进交付验证，保留现有权限与边界',
        ...(operation === 'reflect'
          ? { heading: '## Execution', public: false }
          : {
              patch: {
                heading: '## Execution',
                before: '粘贴该标题下完整原文（含换行）',
                after: '粘贴局部修改后的完整正文',
              },
              rationale: '说明为什么这一处修改有助于目标',
            }),
      };
    }
    if (generation === epoch.current) {
      setJson(JSON.stringify(command, null, 2));
      return command;
    }
  }
  function execute() {
    return run(async () => {
      const command: unknown = JSON.parse(json);
      if (operation === 'diagnose') return feature.api.diagnose(command as DiagnoseCommand);
      if (operation === 'propose') return feature.api.propose(command as ProposalCommand);
      if (operation === 'reflect') return feature.api.reflect(command as ReflectCommand);
      return feature.api.createArena(command as ArenaCommand);
    });
  }
  function control(action: ArenaControl['action']) {
    if (!arena) return;
    const signature = `${arena.id}:${arena.version}:${action}`;
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: crypto.randomUUID() };
    const command: ArenaControl = {
      request_id: pending.current.id,
      expected_version: arena.version,
      action,
    };
    return run(() => feature.api.control(arena.id, command));
  }
  function submit() {
    if (!proposal || !arena) return;
    const signature = `submit:${proposal.id}:${proposal.version}:${arena.id}`;
    if (pending.current?.signature !== signature)
      pending.current = { signature, id: crypto.randomUUID() };
    const requestId = pending.current.id;
    return run(async () => {
      const assets = await feature.assets(project);
      return feature.api.submit(proposal.id, {
        request_id: requestId,
        expected_version: proposal.version,
        arena_id: arena.id,
        expected_learning_revision: assets.candidates_revision,
        direction_reviewed: reviewed,
      });
    });
  }
  return (
    <section className="module-page evolution-page delegation-page">
      <p className="eyebrow">技能改进</p>
      <h1>资产进化</h1>
      <p className="module-description">
        用独立证据诊断问题，比较基线、局部补丁与移除技能的结果，再提交学习候选。
      </p>
      {loading && <p role="status">正在读取进化工作台…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !projects.length && <p>请先在资产页面创建项目并启用一个 Skill。</p>}
      <label>
        进化项目
        <select
          aria-label="进化项目"
          disabled={busy}
          value={project}
          onChange={(e) => setProject(e.target.value)}
        >
          <option value="">选择项目</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
      </label>
      <button
        className="secondary-button"
        disabled={!project || busy}
        onClick={() => void run(refresh)}
      >
        刷新进化记录
      </button>
      {status && (
        <p>
          每组至少 {status.min_repeats} 次，至少 {status.min_development_families}{' '}
          个独立开发集家族；改进还需统计证据与消融支持。
        </p>
      )}
      <div className="settings-card">
        <h2>诊断与候选</h2>
        <p>
          工具故障、执行能力不足和信息不足需要各自处理。反思仅使用训练证据，单次生成会保留费用与失败原因。
        </p>
        <label>
          操作
          <select
            aria-label="进化操作"
            value={operation}
            disabled={busy}
            onChange={(e) => {
              setOperation(e.target.value as Operation);
              setJson('');
            }}
          >
            {Object.entries(labels).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary-button"
          disabled={!project || busy}
          onClick={() => void run(example)}
        >
          填写命令示例
        </button>
        <label>
          进化命令 JSON
          <textarea
            aria-label="进化命令 JSON"
            rows={12}
            value={json}
            onChange={(e) => setJson(e.target.value)}
            disabled={busy}
          />
        </label>
        <button disabled={!json || busy || !project} onClick={() => void execute()}>
          {labels[operation]}
        </button>
        {result && (
          <details open>
            <summary>最近操作结果</summary>
            <pre>{result}</pre>
          </details>
        )}
      </div>
      <div className="settings-card">
        <h2>候选差异与门禁</h2>
        {!proposals.length && <p>暂无候选。先选择证据诊断，再提出一个有边界的局部补丁。</p>}
        <select
          aria-label="进化候选"
          disabled={busy}
          value={proposalId}
          onChange={(e) => {
            setProposalId(e.target.value);
            setReviewed(false);
          }}
        >
          <option value="">选择候选</option>
          {proposals.map((p) => (
            <option key={p.id} value={p.id}>
              {p.command.asset_id} · {p.status} · {p.id.slice(0, 8)}
            </option>
          ))}
        </select>
        {proposal && (
          <>
            <p>方向：{proposal.command.direction}</p>
            <p>状态：{proposal.status} · 未启用</p>
            <p>{proposal.reasons.join('；')}</p>
            <pre aria-label="候选差异">{proposal.diff}</pre>
            {proposal.gates.map((g) => (
              <p key={g.name}>
                {g.name}：{g.verdict} {g.reasons.join('；')}
              </p>
            ))}
          </>
        )}
      </div>
      <div className="settings-card">
        <h2>隔离评测</h2>
        {!arenas.length && <p>暂无评测。冻结案例、重复次数、模型、预算和检查点后才可开始。</p>}
        <select
          aria-label="隔离评测"
          disabled={busy}
          value={arenaId}
          onChange={(e) => {
            setArenaId(e.target.value);
            setReviewed(false);
          }}
        >
          <option value="">选择评测</option>
          {arenas.map((a) => (
            <option key={a.id} value={a.id}>
              {a.status} · {a.id.slice(0, 8)}
            </option>
          ))}
        </select>
        {arena && (
          <>
            <p>
              {arena.status}：{arena.reason}
            </p>
            <p>
              已确认调用 {arena.total_model_calls}，未知调用 {arena.unknown_model_calls}，费用{' '}
              {money(arena.total_cost_microusd)}（仅已确认部分）
            </p>
            {(['start', 'resume', 'approve_current', 'cancel'] as const).map((action, i) => (
              <button
                key={action}
                className="secondary-button"
                disabled={
                  busy ||
                  (action === 'start'
                    ? arena.status !== 'draft'
                    : action === 'resume'
                      ? arena.status !== 'blocked'
                      : action === 'approve_current'
                        ? arena.status !== 'waiting_approval'
                        : ['complete', 'cancelled'].includes(arena.status))
                }
                onClick={() => void control(action)}
              >
                {['开始隔离评测', '恢复当前评测', '批准当前文件改动', '取消隔离评测'][i]}
              </button>
            ))}
            {arena.trials.map((t) => (
              <details key={t.id} open={t.id === arena.current_trial}>
                <summary>
                  {t.case_id} · {t.repeat + 1} · {t.variant} · {t.status} / {t.outcome}
                </summary>
                <p>工作区：{t.workspace_id}</p>
                {t.run_id && (
                  <a href={`?view=agent&run=${encodeURIComponent(t.run_id)}`}>查看运行</a>
                )}
                <p>{t.reasons.join('；')}</p>
                {t.pending_preview && <pre>{t.pending_preview}</pre>}
                <p>
                  独立检查 {t.environment_verified ? '已确认' : '待确认'}，工具检查点{' '}
                  {t.checkpoints_followed ? '通过' : '待确认'}
                </p>
              </details>
            ))}
            {arena.gates.map((g) => (
              <p key={g.name}>
                {g.name}：{g.verdict} {g.reasons.join('；')}
              </p>
            ))}
          </>
        )}
        <label>
          <input
            type="checkbox"
            checked={reviewed}
            disabled={busy}
            onChange={(e) => setReviewed(e.target.checked)}
          />
          我已核对候选 diff、改进方向与独立评测证据
        </label>
        <button
          disabled={
            !reviewed ||
            busy ||
            !proposal ||
            !arena ||
            arena.status !== 'complete' ||
            proposal.current_arena_id !== arena.id
          }
          onClick={() => void submit()}
        >
          提交学习候选
        </button>
        <p>证据不足会保留在待审核队列；正式启用需要独立发布审核。</p>
      </div>
      <div className="settings-card">
        <h2>Playbook 与生成记录</h2>
        {!playbook.length && <p>暂无改进记录。</p>}
        {playbook.map((p) => (
          <details key={p.id}>
            <summary>
              {p.direction} · {p.outcome}
            </summary>
            <p>{p.reasons.join('；')}</p>
            <code>{p.parent_sha256}</code>
          </details>
        ))}
        {generations.map((g) => (
          <p key={g.id}>
            {g.status}：{g.reason} · {g.receipt?.dispatch ?? '待核对'} ·{' '}
            {money(g.receipt?.cost_microusd ?? null)}
          </p>
        ))}
      </div>
    </section>
  );
}
