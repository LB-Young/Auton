import { useEffect, useRef, useState } from 'react';
import type {
  Project,
  ReleaseRecord,
  ReleaseStatus,
  ReleasePlanCommand,
} from '../../shared/contracts';
import type { ReleaseFeature } from './factory';
const pretty = (v: unknown) => JSON.stringify(v, null, 2);
export function Releases({ feature }: { feature: ReleaseFeature }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [records, setRecords] = useState<ReleaseRecord[]>([]);
  const [status, setStatus] = useState<ReleaseStatus | null>(null);
  const [json, setJson] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [risks, setRisks] = useState<Record<string, boolean>>({});
  const epoch = useRef(0);
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
  useEffect(() => {
    const generation = ++epoch.current;
    setRecords([]);
    setRisks({});
    if (!project) return;
    setJson(
      pretty({
        request_id: crypto.randomUUID(),
        project_id: project,
        kind: 'genome',
        source_id: '',
        mode: 'canary',
        percentage: 5,
        scope: { domains: ['general'], languages: ['zh', 'en'], data_domains: ['public'] },
        report_ids: [],
        baseline_report_ids: [],
      }),
    );
    feature.api
      .list(project)
      .then((r) => {
        if (epoch.current === generation) setRecords(r);
      })
      .catch((e: Error) => {
        if (epoch.current === generation) setError(e.message);
      });
    return () => {
      epoch.current++;
    };
  }, [feature, project]);
  async function action(work: () => Promise<unknown>) {
    const generation = epoch.current;
    setBusy(true);
    setError('');
    try {
      await work();
      const r = await feature.api.list(project);
      if (generation === epoch.current) {
        setRecords(r);
        setRisks({});
      }
    } catch (e) {
      if (generation === epoch.current) setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="module-page" aria-label="发布控制面">
      <p className="eyebrow">M20 · 独立批准与运行版本</p>
      <h1>发布与回滚</h1>
      <p className="module-description">
        审核独立证据，再批准固定范围。训练不会自动上线；决策执行继续由教师负责。
      </p>
      {loading && <p role="status">正在加载发布状态…</p>}
      {error && <p role="alert">{error}</p>}
      {status && (
        <div className="settings-card">
          <p>自动批准：关闭 · 决策来源：教师 · 至少 {status.min_independent_families} 个独立家族</p>
          <p>
            暂停停止分配新任务；回滚撤销任务执行权，等待安全检查点对账。远程回退仍遵守隐私边界。
          </p>
        </div>
      )}
      {!loading && projects.length === 0 && <p>请先在资产页面建立项目。</p>}
      <label>
        发布项目
        <select
          aria-label="发布项目"
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
      {project && (
        <div className="settings-card">
          <h2>创建发布报告</h2>
          <label>
            发布计划 JSON
            <textarea
              aria-label="发布计划 JSON"
              rows={16}
              value={json}
              onChange={(e) => setJson(e.target.value)}
            />
          </label>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() =>
              void action(() => {
                const c = JSON.parse(json) as ReleasePlanCommand;
                return feature.api.plan({ ...c, project_id: project });
              })
            }
          >
            检查发布证据
          </button>
        </div>
      )}
      {project && records.length === 0 && <p>当前项目还没有发布报告。</p>}
      {records.map((r) => (
        <article className="settings-card" key={r.id}>
          <h2>
            {r.command.kind} · {r.status}
          </h2>
          <p>
            版本 {r.version} · {r.command.mode} · {r.command.percentage}% · 独立家族{' '}
            {r.report.independent_families}
          </p>
          <code>{r.id}</code>
          <p>{r.reason}</p>
          {!r.current_evidence_valid && <p role="alert">证据已变化，不能批准或激活。</p>}
          <details>
            <summary>范围与冻结证据</summary>
            <pre>
              {pretty({
                scope: r.command.scope,
                source: r.command.source_id,
                report: r.report,
                affected_runs: r.affected_run_ids,
                observations: r.observation_ids,
              })}
            </pre>
          </details>
          <ul>
            {r.report.blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
          <label>
            <input
              type="checkbox"
              checked={!!risks[r.id]}
              disabled={busy}
              onChange={(e) => setRisks({ ...risks, [r.id]: e.target.checked })}
            />
            我已审核此版本范围、风险与回滚条件
          </label>
          <button
            className="secondary-button"
            disabled={busy || !risks[r.id] || r.status !== 'ready' || !r.current_evidence_valid}
            onClick={() =>
              void action(() =>
                feature.api.approve(r.id, {
                  request_id: crypto.randomUUID(),
                  expected_version: r.version,
                  expected_evidence_digest: r.report.evidence_digest,
                  risks_reviewed: true,
                }),
              )
            }
          >
            批准此报告
          </button>
          <button
            className="secondary-button"
            disabled={
              busy || !['approved', 'activating'].includes(r.status) || !r.current_evidence_valid
            }
            onClick={() =>
              void action(() =>
                feature.api.control(r.id, {
                  request_id: crypto.randomUUID(),
                  expected_version: r.version,
                  action: 'activate',
                }),
              )
            }
          >
            激活批准范围
          </button>
          {(['pause', 'rollback'] as const).map((a) => (
            <button
              key={a}
              className="secondary-button"
              disabled={busy || !['active', 'paused', 'rollback_pending'].includes(r.status)}
              onClick={() =>
                void action(() =>
                  feature.api.control(r.id, {
                    request_id: crypto.randomUUID(),
                    expected_version: r.version,
                    action: a,
                  }),
                )
              }
            >
              {a === 'pause'
                ? '暂停新分配'
                : r.status === 'rollback_pending'
                  ? '重试回滚对账'
                  : '回滚'}
            </button>
          ))}
          {r.command.kind === 'executor_model' && !r.approval_event_id && (
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() => void action(() => feature.api.validation(r.id))}
            >
              预热并授权隔离验证
            </button>
          )}
          <p>隔离验证任务和监控报告可通过发布 API 提交；没有独立报告时，激活保持关闭。</p>
        </article>
      ))}
    </section>
  );
}
