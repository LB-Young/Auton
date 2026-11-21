import { useEffect, useRef, useState } from 'react';
import type {
  Project,
  Schedule,
  ScheduleCommand,
  BackgroundJob,
  OperationsStatus,
  TelemetrySample,
  OperationsAlert,
} from '../../shared/contracts';
import type { OperationsFeature } from './factory';
const pretty = (value: unknown) => JSON.stringify(value, null, 2);
export function Operations({ feature }: { feature: OperationsFeature }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [status, setStatus] = useState<OperationsStatus | null>(null);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [samples, setSamples] = useState<TelemetrySample[]>([]);
  const [alerts, setAlerts] = useState<OperationsAlert[]>([]);
  const [json, setJson] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [backupId, setBackupId] = useState('');
  const [sha, setSha] = useState('');
  const [confirm, setConfirm] = useState(false);
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
    setSchedules([]);
    setJobs([]);
    setSamples([]);
    setAlerts([]);
    setResult('');
    if (!project) return;
    setJson(
      pretty({
        request_id: crypto.randomUUID(),
        project_id: project,
        operation: { kind: 'telemetry' },
        enabled: false,
        confirm_background_actions: false,
        expires_at: Math.floor(Date.now() / 1000) + 86400,
        interval_seconds: 3600,
        repeat: false,
        window: { start_hour_utc: 0, end_hour_utc: 24 },
        budget_microusd: 0,
        depends_on: [],
      }),
    );
    let fetching = false;
    async function refresh() {
      if (fetching) return;
      fetching = true;
      try {
        const [s, j, p, a, state] = await Promise.all([
          feature.api.schedules(project),
          feature.api.jobs(project),
          feature.api.samples(project),
          feature.api.alerts(project),
          feature.api.status(),
        ]);
        if (generation === epoch.current) {
          setSchedules(s);
          setJobs(j);
          setSamples(p);
          setAlerts(a);
          setStatus(state);
        }
      } catch (e) {
        if (generation === epoch.current) setError((e as Error).message);
      } finally {
        fetching = false;
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 5000);
    return () => {
      clearInterval(timer);
      epoch.current++;
    };
  }, [feature, project]);
  async function action(work: () => Promise<unknown>) {
    const generation = epoch.current;
    setBusy(true);
    setError('');
    try {
      const value = await work();
      const [s, j, p, a, state] = await Promise.all([
        feature.api.schedules(project),
        feature.api.jobs(project),
        feature.api.samples(project),
        feature.api.alerts(project),
        feature.api.status(),
      ]);
      if (generation === epoch.current) {
        setResult(pretty(value));
        setSchedules(s);
        setJobs(j);
        setSamples(p);
        setAlerts(a);
        setStatus(state);
      }
    } catch (e) {
      if (generation === epoch.current) setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="module-page control-page" aria-label="后台调度与监控">
      <p className="eyebrow">M21 · 有界后台工作流</p>
      <h1>后台运行与监控</h1>
      <p className="module-description">
        前台优先，固定输入，失败按同一请求恢复。后台没有批准或发布权。
      </p>
      {loading && <p role="status">正在加载后台状态…</p>}
      {error && <p role="alert">{error}</p>}
      {status && (
        <div className="settings-card">
          <p>
            {status.enabled ? '宿主调度已启用' : '宿主调度未启用。'} · 当前身份
            {status.owner_paused ? '已暂停' : '允许按计划运行'}
          </p>
          <p>
            付费、数据、训练命令只执行一次；周期计划仅用于监控和监控数据保留。训练需要足够新数据，永远不会自动发布。
          </p>
          {status.last_error && <p role="alert">{status.last_error}</p>}
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void action(() => feature.api.pause(!status.owner_paused))}
          >
            {status.owner_paused ? '恢复当前身份调度' : '暂停当前身份调度'}
          </button>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void action(() => feature.api.tick())}
          >
            执行一次调度检查
          </button>
        </div>
      )}
      {!loading && !projects.length && <p>请先建立项目，再配置后台任务。</p>}
      <label>
        后台项目
        <select
          aria-label="后台项目"
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
          <h2>固定范围的后台计划</h2>
          <label>
            后台计划 JSON
            <textarea
              aria-label="后台计划 JSON"
              rows={15}
              value={json}
              onChange={(e) => setJson(e.target.value)}
            />
          </label>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() =>
              void action(() => {
                const c = JSON.parse(json) as ScheduleCommand;
                if (c.project_id !== project) throw new Error('计划项目必须与当前项目一致');
                return feature.api.schedule(c);
              })
            }
          >
            保存后台计划
          </button>
        </div>
      )}
      <h2>计划与资源窗口</h2>
      {!schedules.length && <p>当前项目暂无后台计划。</p>}
      {schedules.map((s) => (
        <article className="settings-card" key={s.id}>
          <h3>
            {s.command.operation.kind} · {s.enabled ? '允许' : '暂停'}
          </h3>
          <p>
            UTC {s.command.window.start_hour_utc}:00 – {s.command.window.end_hour_utc}:00 ·{' '}
            {s.command.repeat ? '周期监控' : '一次性'} · {s.reason}
          </p>
          <details>
            <summary>授权范围</summary>
            <pre>
              {pretty({
                id: s.id,
                operation: s.command.operation,
                expires_at: s.command.expires_at,
                budget_microusd: s.command.budget_microusd,
                depends_on: s.command.depends_on,
              })}
            </pre>
          </details>
          <button
            className="secondary-button"
            disabled={busy || (!s.enabled && !s.command.confirm_background_actions)}
            onClick={() =>
              void action(() =>
                feature.api.controlSchedule(s.id, {
                  request_id: crypto.randomUUID(),
                  expected_version: s.version,
                  action: s.enabled ? 'pause' : 'resume',
                }),
              )
            }
          >
            {s.enabled ? '暂停计划' : '恢复计划'}
          </button>
        </article>
      ))}
      <h2>后台队列</h2>
      {!jobs.length && <p>当前没有后台作业。</p>}
      {jobs.map((j) => (
        <article className="settings-card" key={j.id}>
          <h3>
            {j.operation.kind} · {j.status}
          </h3>
          <p>{j.reason}</p>
          <p>
            尝试 {j.attempts} · 故障 {j.failures} · 成本{' '}
            {j.actual_cost_microusd === null ? '未知，保留预算' : j.actual_cost_microusd + ' μUSD'}
          </p>
          <details>
            <summary>运行标识</summary>
            <pre>
              {pretty({
                id: j.id,
                external_id: j.external_id,
                next_due: j.next_due,
                lease_until: j.lease_until,
                result_digest: j.result_digest,
              })}
            </pre>
          </details>
          {(['pause', 'resume', 'cancel'] as const).map((a) => (
            <button
              className="secondary-button"
              key={a}
              disabled={
                busy || ['succeeded', 'failed', 'cancelled', 'attention'].includes(j.status)
              }
              onClick={() =>
                void action(() =>
                  feature.api.controlJob(j.id, {
                    request_id: crypto.randomUUID(),
                    expected_version: j.version,
                    action: a,
                  }),
                )
              }
            >
              {a === 'pause' ? '暂停作业' : a === 'resume' ? '恢复作业' : '取消作业'}
            </button>
          ))}
        </article>
      ))}
      <h2>状态变化与趋势</h2>
      <p>告警仅保留在此控制面，状态不变时不重复发出；通过率为描述性运行指标，不代表因果收益。</p>
      {!alerts.length && <p>暂无告警。</p>}
      {alerts.map((a) => (
        <p key={a.id}>
          {a.active ? '待处理' : '已恢复'} · {a.code} ·{' '}
          {new Date(a.changed_at * 1000).toLocaleString()}
        </p>
      ))}
      {!samples.length && <p>暂无监控样本。宿主启用并执行监控计划后显示。</p>}
      {samples.slice(0, 20).map((s) => (
        <div className="settings-card" key={s.id}>
          <p>
            {new Date(s.created_at * 1000).toLocaleString()} · 任务 {s.runs} · 成功/失败 {s.passed}/
            {s.failed} · 已知模型成本 {s.known_cost_microusd} μUSD · 未知用量/副作用{' '}
            {s.unknown_charges} · 待复核 {s.review_backlog}
          </p>
          {s.drift_advisory && <p>运行表现较基线下降，需要独立复核。</p>}
        </div>
      ))}
      <div className="settings-card">
        <h2>调度状态备份与恢复</h2>
        <p>
          仅备份当前身份的调度状态和监控记录，不包含模型、上游业务库或密钥。恢复要求空目标并默认暂停。
        </p>
        <button
          className="secondary-button"
          disabled={busy || !project}
          onClick={() => void action(() => feature.api.backup(crypto.randomUUID()))}
        >
          创建调度备份
        </button>
        <label>
          备份 ID
          <input
            aria-label="备份 ID"
            value={backupId}
            onChange={(e) => setBackupId(e.target.value)}
          />
        </label>
        <label>
          备份 SHA256
          <input aria-label="备份 SHA256" value={sha} onChange={(e) => setSha(e.target.value)} />
        </label>
        <label>
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
          确认当前身份的目标调度状态为空
        </label>
        <button
          className="secondary-button"
          disabled={busy || !project || !confirm || backupId.length !== 64 || sha.length !== 64}
          onClick={() =>
            void action(() =>
              feature.api.restore({
                backup_id: backupId,
                expected_sha256: sha,
                confirm_empty_target: confirm,
              }),
            )
          }
        >
          恢复并保持暂停
        </button>
      </div>
      {result && (
        <details open>
          <summary>最近操作结果</summary>
          <pre>{result}</pre>
        </details>
      )}
    </section>
  );
}
