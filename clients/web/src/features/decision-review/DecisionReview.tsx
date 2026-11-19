import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  AgentRun,
  CalibrationView,
  HumanRevision,
  MetaCaseCommand,
  Project,
  ReviewCommand,
  ReviewRecord,
  ReviewStatus,
} from '../../shared/contracts';
import type { DecisionReviewFeature } from './factory';

type Operation = 'review' | 'revise' | 'meta';
const names = { review: '执行两阶段复核', revise: '保存人工修订', meta: '提交独立人工标注' };
const pretty = (value: unknown) => JSON.stringify(value, null, 2);

export function DecisionReview({ feature }: { feature: DecisionReviewFeature }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [runId, setRunId] = useState('');
  const [records, setRecords] = useState<ReviewRecord[]>([]);
  const [selected, setSelected] = useState('');
  const [status, setStatus] = useState<ReviewStatus | null>(null);
  const [calibrations, setCalibrations] = useState<CalibrationView[]>([]);
  const [operation, setOperation] = useState<Operation>('review');
  const [json, setJson] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const epoch = useRef(0);
  const record = records.find((r) => r.id === selected);
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
    const [r, t, c] = await Promise.all([
      feature.api.list(project),
      feature.runs(project),
      feature.api.calibrations(),
    ]);
    if (generation !== epoch.current) return;
    setRecords(r);
    setRuns(t);
    setCalibrations(c);
    setSelected((id) => (r.some((v) => v.id === id) ? id : (r.at(-1)?.id ?? '')));
    setRunId((id) =>
      t.some((v) => v.id === id) ? id : (t.find((v) => v.judgments.length)?.id ?? ''),
    );
  }, [feature, project]);
  useEffect(() => {
    epoch.current++;
    setRecords([]);
    setRuns([]);
    setCalibrations([]);
    setJson('');
    setError('');
    refresh().catch((e: Error) => setError(e.message));
  }, [refresh]);
  async function action(work: () => Promise<unknown>) {
    setBusy(true);
    setError('');
    const generation = epoch.current;
    try {
      await work();
      if (generation === epoch.current) await refresh();
    } catch (e) {
      if (generation === epoch.current) setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function example() {
    return action(async () => {
      const id = crypto.randomUUID();
      let command: unknown;
      if (operation === 'review') {
        const run = runs.find((r) => r.id === runId);
        const judgment = run?.judgments[0];
        const report = (await feature.reports(project)).find(
          (r) =>
            r.run_id === run?.id &&
            r.checkpoint_version === run.version &&
            r.current_evidence_valid,
        );
        command = {
          request_id: id,
          project_id: project,
          run_id: run?.id ?? '',
          expected_run_version: run?.version ?? 0,
          judgment_id: judgment?.request_id ?? '',
          question_id: judgment?.answers[0]?.question_id ?? '',
          assessment_report_id: report?.id ?? null,
          public: false,
        };
      } else if (operation === 'revise')
        command = {
          request_id: id,
          expected_version: record?.version ?? 0,
          proposed_verdict: 'HOLD',
          reason: '说明新的观察、分歧或需要补充的证据。',
          evidence_refs: record ? [record.subject.before_evidence[0].id] : [],
        };
      else
        command = {
          request_id: id,
          review_id: record?.id ?? '',
          expected_review_version: record?.version ?? 0,
          family: '填写独立任务家族',
          origin_group: '填写同源组',
          gold: 'HOLD',
          explanation: '填写独立人工判断依据，不使用模型生成金标。',
          evidence_refs: record ? [record.subject.before_evidence[0].id] : [],
          confirm_independent_human_annotation: false,
        };
      setJson(pretty(command));
    });
  }
  function execute() {
    return action(async () => {
      const input: unknown = JSON.parse(json);
      if (operation === 'review') {
        const value = await feature.api.review(input as ReviewCommand);
        setSelected(value.id);
      } else if (operation === 'revise') {
        if (!record) throw new Error('请先选择复核记录');
        await feature.api.revise(record.id, input as HumanRevision);
      } else await feature.api.annotateMeta(input as MetaCaseCommand);
    });
  }
  return (
    <section className="module-page evolution-page delegation-page">
      <p className="eyebrow">独立决策复核</p>
      <h1>决策轨迹复核</h1>
      <p className="module-description">
        先审查当时依据，再审查后续贡献。成功、失败和模型信心都不能直接决定训练资格。
      </p>
      {loading && <p role="status">正在加载复核工作台…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !projects.length && <p>先创建项目并执行任务，才能查看逐次决策。</p>}
      <label>
        复核项目
        <select
          aria-label="复核项目"
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
        disabled={busy || !project}
        className="secondary-button"
        onClick={() => void action(refresh)}
      >
        刷新复核记录
      </button>
      {status && (
        <p>
          独立 reviewer：{status.reviewer_model} · {status.rubric_revision}
        </p>
      )}
      <div className="settings-card">
        <h2>复核与人工队列</h2>
        <p>
          未采用答案不能继承执行成功。DROP 排除正向训练，HOLD 等待补证；人工 KEEP
          也需要通过证据与校准门禁。
        </p>
        <label>
          轨迹来源
          <select
            aria-label="复核轨迹"
            value={runId}
            disabled={busy}
            onChange={(e) => setRunId(e.target.value)}
          >
            <option value="">选择有判断记录的运行</option>
            {runs
              .filter((r) => r.judgments.length)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.command.goal.slice(0, 45)} · v{r.version} · {r.status}
                </option>
              ))}
          </select>
        </label>
        <label>
          操作
          <select
            aria-label="复核操作"
            value={operation}
            disabled={busy}
            onChange={(e) => {
              setOperation(e.target.value as Operation);
              setJson('');
            }}
          >
            {Object.entries(names).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary-button"
          disabled={
            busy ||
            !project ||
            (operation === 'review' ? !runs.some((r) => r.id === runId) : !record)
          }
          onClick={() => void example()}
        >
          填写复核命令
        </button>
        <label>
          复核命令 JSON
          <textarea
            aria-label="复核命令 JSON"
            rows={10}
            value={json}
            disabled={busy}
            onChange={(e) => setJson(e.target.value)}
          />
        </label>
        <button disabled={busy || !json || !project} onClick={() => void execute()}>
          {busy ? '正在处理复核…' : names[operation]}
        </button>
      </div>
      <div className="settings-card">
        <h2>逐次判断与影响链</h2>
        {!records.length && <p>暂无复核记录。选择一条轨迹，冻结原问题和具体答案后开始。</p>}
        <label>
          复核记录
          <select
            aria-label="复核记录"
            disabled={busy}
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">选择复核</option>
            {records.map((r) => (
              <option key={r.id} value={r.id}>
                {r.command.question_id} · {r.verdict} · {r.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        {record && (
          <>
            <p aria-label="决策样本状态">
              {record.verdict} · {record.status} ·{' '}
              {record.positive_training_eligible ? '可进入正样本候选' : '不进入正向训练'}
            </p>
            <p>{record.reason_codes.join('；')}</p>
            <p>
              证据：{record.evidence_current ? '当前有效' : '已变化，需要重评'} · 是否采用：
              {record.subject.decision.adopted ? '是' : '否'}
            </p>
            <details>
              <summary>原始判断与版本</summary>
              <pre>
                {pretty({
                  request: record.subject.request,
                  answer: record.subject.answer,
                  decision_source: record.subject.decision.source,
                  source_digest: record.subject.source_digest,
                })}
              </pre>
            </details>
            <details open>
              <summary>阶段 A：仅看决策前状态</summary>
              <pre>{record.subject.request.state}</pre>
              {record.subject.before_evidence.map((f) => (
                <p key={f.id}>
                  <code>{f.id}</code>：{f.text}
                </p>
              ))}
              <pre>{pretty(record.stage_a)}</pre>
            </details>
            <details open>
              <summary>阶段 B：后续实际贡献</summary>
              {record.subject.after_evidence.map((f) => (
                <details key={f.id}>
                  <summary>
                    {f.kind} · {f.id.slice(-20)}
                  </summary>
                  <code>{f.id}</code>
                  <pre>{f.text}</pre>
                </details>
              ))}
              <pre>{pretty(record.stage_b)}</pre>
            </details>
            {record.human_revisions.length > 0 && (
              <details open>
                <summary>人工修订历史</summary>
                <pre>{pretty(record.human_revisions)}</pre>
              </details>
            )}
          </>
        )}
      </div>
      <div className="settings-card">
        <h2>Reviewer 人工校准</h2>
        <p>
          独立人工金标覆盖 KEEP / DROP / HOLD，并按同源家族去重。人工 meta
          永不进入训练；校准不足时保持关闭。
        </p>
        {calibrations.map((c, i) => (
          <div key={c.reviewer_signature ?? String(i)}>
            <p>
              自动准入：{c.eligible ? '门禁通过' : '关闭'} · 独立家族 {c.independent_families}
            </p>
            <p>
              KEEP 污染率置信上界：
              {c.keep_contamination_upper === null
                ? '未知'
                : `${(100 * c.keep_contamination_upper).toFixed(2)}%`}
            </p>
            <p>{c.reasons.join('；')}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
