import { useEffect, useRef, useState } from 'react';
import type {
  AgentRun,
  Aggregate,
  AssessmentStatus,
  BatchEvaluation,
  BlindWindowCommand,
  CalibrationCommand,
  CalibrationReport,
  CaseBank,
  Comparison,
  EvalReport,
  EvaluateCommand,
  ImportCases,
  Project,
  RunPage,
  WindowView,
} from '../../shared/contracts';
import type { AssessmentFeature } from './factory';

const outcome: Record<string, string> = {
  pass: '通过',
  fail: '失败',
  unknown: '未知',
  environment_error: '环境故障',
  incomplete: '未完成',
};
const sources: Record<string, string> = {
  deterministic: '独立检查',
  'model-judge': '模型裁判',
  human: '人工偏好',
  'unverified-self-report': '未核验自述',
};
const money = (value: number | null) =>
  value === null ? '未知' : `$${(value / 1000000).toFixed(6)}`;

export function Assessment({ feature }: { feature: AssessmentFeature }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [status, setStatus] = useState<AssessmentStatus | null>(null);
  const [bank, setBank] = useState<CaseBank | null>(null);
  const [windows, setWindows] = useState<WindowView[]>([]);
  const [calibrations, setCalibrations] = useState<CalibrationReport[]>([]);
  const [page, setPage] = useState<RunPage | null>(null);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [reports, setReports] = useState<EvalReport[]>([]);
  const [aggregate, setAggregate] = useState<Aggregate | null>(null);
  const [detail, setDetail] = useState<EvalReport | null>(null);
  const [baseline, setBaseline] = useState('');
  const [candidate, setCandidate] = useState('');
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [semantic, setSemantic] = useState(false);
  const [repeats, setRepeats] = useState(2);
  const [advanced, setAdvanced] = useState('import');
  const [command, setCommand] = useState('');
  const [result, setResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  const pending = useRef<{ signature: string; command: EvaluateCommand } | null>(null);
  const seedRequest = useRef<{ revision: string; id: string } | null>(null);
  useEffect(() => {
    let live = true;
    feature
      .projects()
      .then((values) => {
        if (live) {
          setProjects(values);
          setProject(values[0]?.id ?? '');
        }
      })
      .catch((e: Error) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
      generation.current++;
    };
  }, [feature]);
  useEffect(() => {
    const current = ++generation.current;
    setLoading(true);
    setError('');
    setRun(null);
    setDetail(null);
    setComparison(null);
    setBaseline('');
    setCandidate('');
    setReports([]);
    setAggregate(null);
    setPage(null);
    Promise.all([
      feature.api.status(),
      feature.api.bank(),
      feature.api.windows(),
      feature.api.calibrations(),
      project ? feature.history(project, 0) : Promise.resolve(null),
      project ? feature.api.reports(project) : Promise.resolve([]),
      project ? feature.api.aggregate(project) : Promise.resolve(null),
    ])
      .then(([s, b, w, c, p, r, a]) => {
        if (current !== generation.current) return;
        setStatus(s);
        setBank(b);
        setWindows(w);
        setCalibrations(c);
        setPage(p);
        setReports(r);
        setAggregate(a);
        setLoading(false);
      })
      .catch((e: Error) => {
        if (current === generation.current) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      generation.current++;
    };
  }, [feature, project, refresh]);
  async function perform(action: () => Promise<void>) {
    if (busy) return;
    const current = generation.current;
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      if (current === generation.current) setError(e instanceof Error ? e.message : '请求失败');
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }
  async function evaluate() {
    if (!run) return;
    const signature = JSON.stringify([run.id, run.version, semantic, repeats]);
    if (pending.current?.signature !== signature)
      pending.current = {
        signature,
        command: {
          request_id: crypto.randomUUID(),
          project_id: project,
          run_id: run.id,
          expected_version: run.version,
          semantic,
          repeats,
        },
      };
    const job = await feature.api.evaluate(pending.current.command);
    setResult(job);
    setDetail(job.report);
    setReports(await feature.api.reports(project));
    setAggregate(await feature.api.aggregate(project));
    pending.current = null;
  }
  async function submitAdvanced() {
    const parsed: unknown = JSON.parse(command);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed))
      throw new Error('请输入 JSON 对象');
    // The server validates every field, owner, CAS revision and protected-window reservation.
    const value =
      advanced === 'import'
        ? await feature.api.importCases(parsed as ImportCases)
        : advanced === 'window'
          ? await feature.api.openWindow(parsed as BlindWindowCommand)
          : advanced === 'calibrate'
            ? await feature.api.calibrate(parsed as CalibrationCommand)
            : await feature.api.batch(parsed as BatchEvaluation);
    setResult(value);
    setBank(await feature.api.bank());
    setWindows(await feature.api.windows());
    setCalibrations(await feature.api.calibrations());
    if (project) {
      setReports(await feature.api.reports(project));
      setAggregate(await feature.api.aggregate(project));
    }
  }
  const disabled = busy || loading;
  return (
    <section className="module-page tool-page assessment-page">
      <p className="eyebrow">独立评估 · M13</p>
      <h1>评测</h1>
      <p className="module-description">
        从确切的运行检查点核验结果，分别查看验收、裁判和人工信号。
      </p>
      <p className="module-note">
        未知、环境故障和未完成样本不计入准确率分母。模型自信与用户好评均不等于正确。报告不会自动发布模型。
      </p>
      {loading && <p role="status">正在读取评测状态…</p>}
      {busy && <p role="status">正在执行，请保留请求编号以便重试…</p>}
      {error && (
        <p className="notice-banner" role="alert">
          {error}
        </p>
      )}
      <button
        className="secondary-button"
        disabled={disabled}
        onClick={() => setRefresh((v) => v + 1)}
      >
        刷新评测
      </button>
      {status && (
        <article className="settings-card">
          <h2>裁判与校准</h2>
          <p>
            模型：{status.judge_model} · rubric：{status.rubric_revision}
          </p>
          <p>
            配置：<code>{status.config_digest}</code>
          </p>
          <p>私有裁判日志：{status.private_judge_journal ? '已隔离' : '未隔离，语义评测不可用'}</p>
          <p>
            至少 {status.min_calibration_samples} 个独立任务家族，95% 置信下界至少{' '}
            {status.min_calibration_lower}；校准调用上限 {status.max_calibration_calls}。
          </p>
          {!calibrations.length && (
            <p className="notice-banner">尚无人工元评测校准，语义可信门禁关闭。</p>
          )}
          {calibrations.map((c) => (
            <details key={c.id}>
              <summary>
                {c.passed ? '校准通过 · 仅覆盖声明分组' : '校准未通过'} · {c.samples} 样本 /{' '}
                {c.families} 家族
              </summary>
              <p>
                正例 {c.positive_gold} · 反例 {c.negative_gold} · 已知 {c.known} · 覆盖率{' '}
                {c.coverage} · κ {c.kappa ?? '不可计算'} · 95% 下界 {c.wilson_lower ?? '未知'}
              </p>
              <p>
                重复分歧 {c.repeat_disagreements} · 关键错误 {c.critical_errors} · 关键未知{' '}
                {c.critical_missing}
              </p>
              <p>
                确认费用 {money(c.confirmed_judge_cost_microusd)} · 未知调用 {c.unknown_judge_calls}
              </p>
              <p>{c.reasons.join(' / ')}</p>
              <pre>{JSON.stringify(c.groups, null, 2)}</pre>
            </details>
          ))}
        </article>
      )}
      <article className="settings-card">
        <h2>评测任务</h2>
        {!projects.length && <p>还没有项目，请先在任务页创建项目并运行任务。</p>}
        <label className="judgment-label">
          项目
          <select
            aria-label="评测项目"
            disabled={disabled}
            value={project}
            onChange={(e) => {
              setResult(null);
              setProject(e.target.value);
            }}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </label>
        <label className="judgment-label">
          运行
          <select
            aria-label="评测运行"
            disabled={disabled || !page?.items.length}
            value={run?.id ?? ''}
            onChange={(e) => {
              const id = e.target.value;
              void perform(async () => {
                setDetail(null);
                setRun(id ? await feature.run(id) : null);
              });
            }}
          >
            <option value="">选择运行检查点</option>
            {page?.items.map((r) => (
              <option key={r.id} value={r.id}>
                {r.command.goal.slice(0, 70)} · {r.status} · v{r.version}
              </option>
            ))}
          </select>
        </label>
        {page && page.next_cursor !== null && (
          <button
            className="secondary-button"
            disabled={disabled}
            onClick={() =>
              void perform(async () => {
                const next = await feature.history(project, page.next_cursor!);
                setPage({
                  ...next,
                  items: [
                    ...page.items,
                    ...next.items.filter((r) => !page.items.some((old) => old.id === r.id)),
                  ],
                });
              })
            }
          >
            更多运行
          </button>
        )}
        {page && !page.items.length && <p>当前项目没有可评测的运行。</p>}
        {run && (
          <p>
            固定检查点 v{run.version} · 目标修订 {run.goal_revision} · {run.status}
          </p>
        )}
        <label className="judgment-label">
          <input
            type="checkbox"
            checked={semantic}
            disabled={disabled}
            onChange={(e) => setSemantic(e.target.checked)}
          />
          调用语义裁判（仅公开数据可外发，可能产生费用）
        </label>
        <label className="judgment-label">
          重复次数
          <select
            value={repeats}
            disabled={disabled}
            onChange={(e) => setRepeats(Number(e.target.value))}
          >
            {[1, 2, 3].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <button
          className="secondary-button"
          disabled={disabled || !run}
          onClick={() => void perform(evaluate)}
        >
          评测当前检查点
        </button>
      </article>
      {aggregate && (
        <article className="settings-card" aria-label="评测统计">
          <h2>项目统计 · 描述性结果</h2>
          <p>
            总样本 {aggregate.total} · 已知分母 {aggregate.known_denominator} · 通过{' '}
            {aggregate.passed} · 失败 {aggregate.failed} · 未知 {aggregate.unknown}
          </p>
          <p>
            环境故障 {aggregate.environment_errors} · 未完成 {aggregate.incomplete} · 严重失败{' '}
            {aggregate.critical_failures}
          </p>
          <p>
            通过率{' '}
            {aggregate.pass_rate === null
              ? '不可计算'
              : `${(100 * aggregate.pass_rate).toFixed(1)}%`}{' '}
            · Wilson 95% [{aggregate.wilson_lower ?? '?'}, {aggregate.wilson_upper ?? '?'}]
          </p>
          <p>
            执行已知费用 {money(aggregate.cost_microusd)} · 裁判确认费用下限{' '}
            {money(aggregate.evaluation_cost_microusd)} · 裁判未知调用{' '}
            {aggregate.evaluation_unknown_calls}
          </p>
          <p>
            测试夹具：{aggregate.source_counts.test ?? 0} · 真实运行：
            {aggregate.source_counts.runtime ?? 0} · 独立发布候选行：{aggregate.release_eligible}
          </p>
          <details>
            <summary>分组表现</summary>
            <pre>{JSON.stringify(aggregate.groups, null, 2)}</pre>
          </details>
        </article>
      )}
      <article className="settings-card">
        <h2>报告与证据</h2>
        {!reports.length && <p>尚无评测报告。</p>}
        {reports.map((r) => (
          <button
            className="secondary-button assessment-report"
            key={r.id}
            disabled={busy}
            onClick={() => setDetail(r)}
          >
            {outcome[r.outcome]} · {r.source === 'test' ? '测试夹具' : '真实运行'} · v
            {r.checkpoint_version} · {r.id.slice(0, 12)}
          </button>
        ))}
        {detail && (
          <div aria-label="评测证据">
            <h3>
              {outcome[detail.outcome]} · {detail.split}
            </h3>
            <p>
              环境可比性：{detail.environment_verified ? '运行账本核验通过' : '尚未核验'} · 语义：
              {outcome[detail.semantic_verdict]}
            </p>
            <p>
              发布候选行：
              {detail.quality_release_eligible
                ? '符合本行条件，仍需完整批次与审批'
                : '不符合'} · {detail.reasons.join(' / ')}
            </p>
            <p>
              候选版本：<code>{detail.candidate_revision}</code>
            </p>
            <p>
              检查点：<code>{detail.checkpoint_event_id}</code>
            </p>
            <p>
              执行 {detail.metrics.confirmed_model_calls} 次确认调用 /{' '}
              {detail.metrics.unconfirmed_model_calls} 次未知调用，{detail.metrics.tokens} tokens，
              {money(detail.metrics.cost_microusd)}。
            </p>
            <p>
              工具失败 {detail.metrics.failed_tools} / {detail.metrics.tool_attempts}
              ；额外调用参考值 {detail.metrics.extra_model_calls}（不等于已归因返工）。
            </p>
            {detail.signals.map((signal, i) => (
              <details key={i} open>
                <summary>
                  {sources[signal.source]} · {signal.name} · {outcome[signal.verdict]}
                  {signal.critical ? ' · 关键项' : ''}
                </summary>
                <p>{signal.reason}</p>
                <pre>{signal.evidence.join('\n')}</pre>
              </details>
            ))}
            <details>
              <summary>完整裁判记录</summary>
              <pre>{JSON.stringify(detail.judges, null, 2)}</pre>
            </details>
          </div>
        )}
      </article>
      <article className="settings-card">
        <h2>同条件候选对照</h2>
        <p>配置、证据、预算、价格或环境不同会拒绝比较；同一次运行不能作为独立改进证据。</p>
        {(['baseline', 'candidate'] as const).map((kind) => (
          <label className="judgment-label" key={kind}>
            {kind === 'baseline' ? '基线报告' : '候选报告'}
            <select
              aria-label={kind === 'baseline' ? '基线报告' : '候选报告'}
              disabled={disabled}
              value={kind === 'baseline' ? baseline : candidate}
              onChange={(e) => {
                setComparison(null);
                if (kind === 'baseline') setBaseline(e.target.value);
                else setCandidate(e.target.value);
              }}
            >
              <option value="">选择报告</option>
              {reports.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id.slice(0, 12)} · {outcome[r.outcome]}
                </option>
              ))}
            </select>
          </label>
        ))}
        <button
          className="secondary-button"
          disabled={disabled || !baseline || !candidate}
          onClick={() =>
            void perform(async () =>
              setComparison(await feature.api.compare({ baseline, candidate })),
            )
          }
        >
          比较候选
        </button>
        {comparison && (
          <div role="status">
            <p>{comparison.comparable ? '条件可比，差值仅为描述' : '不可作为改进证据'}</p>
            <p>{comparison.reasons.join(' / ')}</p>
            <p>
              token 差值 {comparison.token_delta} · 费用差值 {money(comparison.cost_delta_microusd)}
            </p>
          </div>
        )}
      </article>
      {bank && (
        <article className="settings-card">
          <h2>隔离题库与盲测窗口</h2>
          <p>
            train {bank.counts.train ?? 0} · development {bank.counts.development ?? 0} · test{' '}
            {bank.counts.test ?? 0} · meta {bank.counts.meta ?? 0}
          </p>
          <p>
            题库版本：<code>{bank.revision}</code>
          </p>
          <p>题库列表仅显示元数据。种子仅包含训练示例；人工元评测金标需单独审核导入。</p>
          <button
            className="secondary-button"
            disabled={disabled}
            onClick={() =>
              void perform(async () => {
                if (seedRequest.current?.revision !== bank.revision)
                  seedRequest.current = { revision: bank.revision, id: crypto.randomUUID() };
                setBank(
                  await feature.api.seed({
                    request_id: seedRequest.current.id,
                    expected_revision: bank.revision,
                  }),
                );
                seedRequest.current = null;
              })
            }
          >
            添加训练种子
          </button>
          <details>
            <summary>题库元数据</summary>
            <pre>{JSON.stringify(bank.cases, null, 2)}</pre>
          </details>
          {!windows.length && <p>还没有盲测窗口。</p>}
          {windows.map((w) => (
            <p key={w.window.id}>
              <code>{w.window.id}</code> · {w.window.split} · {w.used}/{w.window.max_uses} ·{' '}
              {w.current ? '当前分区' : '已失效'}
            </p>
          ))}
          <details>
            <summary>高级：导入、窗口、校准与完整盲测批次</summary>
            <p>
              使用 API 格式 JSON；每个操作填写固定
              request_id，重试保留原文。受保护分区的任务家族不得进入其他分区。
            </p>
            <p>
              开窗字段：request_id、bank_revision、split（test/meta）、purpose（release/calibration）、candidate_revision（测试用报告候选版本，校准用上方配置摘要）。
            </p>
            <p>
              校准字段：request_id、bank_revision、window_id、confirm_public、repeats（2–3）。仅经授权的公开题目可交给远程裁判。
            </p>
            <p>
              批次字段：request_id、project_id、bank_revision、window_id、runs（每个 test case_id
              对应 run_id 与 expected_version）、semantic、repeats。须一次绑定完整测试集。
            </p>
            <label className="judgment-label">
              操作
              <select
                value={advanced}
                disabled={disabled}
                onChange={(e) => {
                  setAdvanced(e.target.value);
                  setCommand('');
                  setResult(null);
                }}
              >
                <option value="import">导入题目</option>
                <option value="window">打开受保护窗口</option>
                <option value="calibrate">人工金标校准</option>
                <option value="batch">完整盲测批次</option>
              </select>
            </label>
            <label className="judgment-label">
              JSON 命令
              <textarea
                aria-label="评测 JSON 命令"
                rows={10}
                value={command}
                disabled={disabled}
                onChange={(e) => setCommand(e.target.value)}
              />
            </label>
            <button
              className="secondary-button"
              disabled={disabled || !command.trim()}
              onClick={() => void perform(submitAdvanced)}
            >
              提交评测命令
            </button>
          </details>
        </article>
      )}
      {result !== null && (
        <details>
          <summary>最近操作回执</summary>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}
