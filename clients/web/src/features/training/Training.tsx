import { useEffect, useRef, useState } from 'react';
import type {
  Project,
  TrainingPlan,
  TrainingPlanCommand,
  TrainingJob,
  TrainingBundle,
  TrainingStatus,
} from '../../shared/contracts';
import type { TrainingFeature } from './factory';
const pretty = (value: unknown) => JSON.stringify(value, null, 2);
export function Training({ feature }: { feature: TrainingFeature }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [status, setStatus] = useState<TrainingStatus | null>(null);
  const [plans, setPlans] = useState<TrainingPlan[]>([]);
  const [jobs, setJobs] = useState<TrainingJob[]>([]);
  const [bundles, setBundles] = useState<TrainingBundle[]>([]);
  const [json, setJson] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
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
    setPlans([]);
    setJobs([]);
    setBundles([]);
    setJson('');
    let active = false;
    async function refresh() {
      if (!project || active) return;
      active = true;
      try {
        const [p, j, b] = await Promise.all([
          feature.api.plans(project),
          feature.api.jobs(project),
          feature.api.bundles(project),
        ]);
        if (epoch.current === generation) {
          setPlans(p);
          setJobs(j);
          setBundles(b);
        }
      } catch (e) {
        if (epoch.current === generation) setError((e as Error).message);
      } finally {
        active = false;
      }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 2000);
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
      await work();
      if (generation !== epoch.current) return;
      const [p, j, b] = await Promise.all([
        feature.api.plans(project),
        feature.api.jobs(project),
        feature.api.bundles(project),
      ]);
      if (generation === epoch.current) {
        setPlans(p);
        setJobs(j);
        setBundles(b);
      }
    } catch (e) {
      if (generation === epoch.current) setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="module-page datasets-page">
      <p className="eyebrow">获准数据 → 基线 → 训练 → 候选复测</p>
      <h1>执行模型训练</h1>
      <p className="module-description">
        训练环境由部署配置决定。每个作业固定模型、模板、数据与预算；完成后生成离线候选，独立评估通过后再进入发布流程。
      </p>
      {loading && <p role="status">正在加载训练模块…</p>}
      {error && <p role="alert">{error}</p>}
      {status && !status.configured && (
        <p role="status">
          训练后端未配置。可先准备训练计划；部署时配置固定版本镜像、基础模型与资源限额。
        </p>
      )}
      {!loading && !projects.length && <p>暂无项目，请先准备通过独立检查的训练与验证数据。</p>}
      <label>
        训练项目
        <select
          aria-label="训练项目"
          value={project}
          disabled={busy}
          onChange={(e) => setProject(e.target.value)}
        >
          {projects.map((p) => (
            <option value={p.id} key={p.id}>
              {p.title}
            </option>
          ))}
        </select>
      </label>
      <div className="settings-card">
        <h2>训练计划</h2>
        <p>
          训练、开发验证、旧任务
          replay、通用锚点保持家族隔离。样本不足时阻塞正式训练；工程探针最多三步，不能作为效果通过依据。
        </p>
        <button
          disabled={!project || busy}
          onClick={() =>
            setJson(
              pretty({
                request_id: crypto.randomUUID(),
                project_id: project,
                base_model_id: status?.model_ids[0] ?? 'configured-base',
                train_artifact_id: '',
                validation_artifact_id: null,
                replay_artifact_id: null,
                anchor_artifact_id: null,
                steps: 100,
                learning_rate: 0.0001,
                rank: 8,
                seed: 42,
                max_sequence_length: 2048,
                engineering_probe: false,
              }),
            )
          }
        >
          准备训练计划
        </button>
        <label>
          训练计划命令
          <textarea
            aria-label="训练计划命令"
            rows={15}
            value={json}
            disabled={busy}
            onChange={(e) => setJson(e.target.value)}
          />
        </label>
        <button
          disabled={!json || busy}
          onClick={() =>
            void action(() => {
              const command = JSON.parse(json) as TrainingPlanCommand;
              if (command.project_id !== project) throw new Error('命令项目必须与当前项目一致');
              return feature.api.plan(command);
            })
          }
        >
          检查并保存计划
        </button>
        {plans.map((p) => (
          <article key={p.id}>
            <h3>
              {p.command.request_id} · {p.status}
            </h3>
            <p>{p.blockers.join('、')}</p>
            <details>
              <summary>数据、资源与固定版本</summary>
              <pre>{pretty(p)}</pre>
            </details>
            <button
              disabled={busy || p.status !== 'ready' || !p.current_evidence_valid}
              onClick={() =>
                void action(() =>
                  feature.api.create({
                    request_id: crypto.randomUUID(),
                    plan_id: p.id,
                    expected_plan_digest: p.manifest_digest,
                  }),
                )
              }
            >
              启动训练作业
            </button>
          </article>
        ))}
      </div>
      <div className="settings-card">
        <h2>训练作业（{jobs.length}）</h2>
        {!jobs.length && <p>暂无训练作业。</p>}
        {jobs.map((j) => (
          <article key={j.id}>
            <h3>
              {j.command.request_id} · {j.status}
            </h3>
            <p>
              已提交 checkpoint 步数 {j.completed_steps} · 第 {j.attempt + 1} 次执行
            </p>
            <p>{j.reason}</p>
            <details>
              <summary>检查进度、谱系与指标</summary>
              <pre>{pretty(j)}</pre>
            </details>
            {(['cancel', 'resume'] as const).map((actionName) => (
              <button
                key={actionName}
                disabled={
                  busy ||
                  (actionName === 'cancel'
                    ? !['queued', 'running', 'interrupted'].includes(j.status)
                    : !['failed', 'interrupted', 'cancelled'].includes(j.status) || !j.checkpoint)
                }
                onClick={() =>
                  void action(() =>
                    feature.api.control(j.id, {
                      request_id: crypto.randomUUID(),
                      expected_version: j.version,
                      action: actionName,
                    }),
                  )
                }
              >
                {actionName === 'cancel' ? '取消作业' : '校验并恢复'}
              </button>
            ))}
          </article>
        ))}
      </div>
      <div className="settings-card">
        <h2>离线模型候选（{bundles.length}）</h2>
        {!bundles.length && <p>暂无模型候选。训练 loss 下降不能替代任务质量、遗忘与部署评测。</p>}
        {bundles.map((b) => (
          <details key={b.id}>
            <summary>
              {b.id.slice(0, 16)} · {b.source_current ? '来源有效' : '来源已撤回或变化'} ·
              待独立发布评估
            </summary>
            <pre>{pretty(b)}</pre>
          </details>
        ))}
      </div>
    </section>
  );
}
