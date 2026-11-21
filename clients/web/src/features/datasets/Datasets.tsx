import { useEffect, useRef, useState } from 'react';
import type {
  DataGrant,
  DataGrantCommand,
  DatasetBuild,
  DatasetSnapshot,
  DatasetWithdrawal,
  Project,
} from '../../shared/contracts';
import type { DatasetsFeature } from './factory';
const pretty = (v: unknown) => JSON.stringify(v, null, 2);
type Operation = 'grant' | 'build' | 'withdraw';
export function Datasets({ feature }: { feature: DatasetsFeature }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState('');
  const [grants, setGrants] = useState<DataGrant[]>([]);
  const [snapshots, setSnapshots] = useState<DatasetSnapshot[]>([]);
  const [operation, setOperation] = useState<Operation>('grant');
  const [json, setJson] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const epoch = useRef(0);
  useEffect(() => {
    let live = true;
    Promise.all([feature.projects(), feature.api.status()])
      .then(([p]) => {
        if (live) {
          setProjects(p);
          setProject(p[0]?.id ?? '');
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
    setJson('');
    setResult('');
    setGrants([]);
    setSnapshots([]);
    if (!project) return;
    Promise.all([feature.api.grants(project), feature.api.list(project)])
      .then(([g, s]) => {
        if (epoch.current === generation) {
          setGrants(g);
          setSnapshots(s);
        }
      })
      .catch((e: Error) => {
        if (epoch.current === generation) setError(e.message);
      });
  }, [feature, project]);
  async function action(work: () => Promise<unknown>) {
    const generation = epoch.current;
    setBusy(true);
    setError('');
    try {
      const value = await work();
      if (generation !== epoch.current) return;
      setResult(pretty(value));
      const [g, s] = await Promise.all([feature.api.grants(project), feature.api.list(project)]);
      if (generation === epoch.current) {
        setGrants(g);
        setSnapshots(s);
      }
    } catch (e) {
      if (generation === epoch.current) setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function example() {
    const generation = epoch.current;
    const [runs, reports] = await Promise.all([feature.runs(project), feature.reports(project)]);
    if (generation !== epoch.current) return;
    const run = runs.find((r) => r.status === 'succeeded');
    const grant = grants.find((g) => !g.revoked);
    const common = { request_id: crypto.randomUUID(), project_id: project };
    setJson(
      pretty(
        operation === 'grant'
          ? {
              ...common,
              run_ids: run ? [run.id] : [],
              purposes: ['executor'],
              data_license_reference: '填写本人拥有或获准训练使用的输入来源与授权范围',
              local_training_authorized: false,
              allow_local_only_data: false,
              teacher_uses: run
                ? [
                    {
                      model_id: run.command.model_id,
                      declared_revision: run.executor_spec.declared_revision,
                      terms_reference: '填写适用版本的模型提供方训练使用条款链接',
                      training_use_confirmed_by_user: false,
                    },
                  ]
                : [],
            }
          : operation === 'build'
            ? {
                ...common,
                kind: 'executor',
                grant_id: grant?.id ?? '',
                subjects: run
                  ? [
                      {
                        run_id: run.id,
                        expected_version: run.version,
                        assessment_report_id:
                          reports.find(
                            (r) => r.run_id === run.id && r.checkpoint_version === run.version,
                          )?.id ?? null,
                        family: 'task-family',
                        origin_group: 'original-source',
                        split: 'train',
                      },
                    ]
                  : [],
              }
            : {
                ...common,
                grant_id: grant?.id ?? '',
                reason: '填写撤回原因；此授权下已有导出将停止后续访问',
              },
      ),
    );
  }
  return (
    <section className="module-page datasets-page">
      <p className="eyebrow">历史记录 → 本地学习数据</p>
      <h1>数据集与谱系</h1>
      <p className="module-description">
        Executor、Router、Decision
        分别构建。先检查授权与来源，再锁定家族划分。test、meta、进化实验输入禁止训练；工程样例禁止导出训练。此页面不启动训练。
      </p>
      {loading && <p role="status">正在读取数据模块…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && projects.length === 0 && <p>暂无项目，请先创建项目并完成带独立验收的任务。</p>}
      <label>
        数据项目
        <select
          aria-label="数据项目"
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
      <div className="settings-card">
        <h2>授权与批次操作</h2>
        <label>
          数据操作
          <select
            aria-label="数据操作"
            value={operation}
            disabled={busy}
            onChange={(e) => {
              setOperation(e.target.value as Operation);
              setJson('');
            }}
          >
            <option value="grant">登记训练授权</option>
            <option value="build">构建不可变快照</option>
            <option value="withdraw">撤回来源授权</option>
          </select>
        </label>
        <p>
          授权默认为关闭。提交前核对来源、用途、模型版本和条款。撤回保留审计记录，并阻止后续下载与使用。
        </p>
        <button disabled={busy || !project} onClick={() => void action(example)}>
          准备数据命令
        </button>
        <label>
          数据命令
          <textarea
            aria-label="数据命令"
            rows={14}
            value={json}
            disabled={busy}
            onChange={(e) => setJson(e.target.value)}
          />
        </label>
        <button
          disabled={busy || !json}
          onClick={() =>
            void action(() => {
              const command = JSON.parse(json);
              if (command.project_id !== project) throw new Error('命令项目必须与当前项目一致');
              return operation === 'grant'
                ? feature.api.grant(command as DataGrantCommand)
                : operation === 'build'
                  ? feature.api.build(command as DatasetBuild)
                  : feature.api.withdraw(command as DatasetWithdrawal);
            })
          }
        >
          {busy ? '处理中…' : '提交数据操作'}
        </button>
      </div>
      <div className="settings-card">
        <h2>来源授权（{grants.length}）</h2>
        {grants.length === 0 && <p>暂无训练授权；历史记录不会自动变成训练材料。</p>}
        {grants.map((g) => (
          <details key={g.id}>
            <summary>
              {g.command.request_id} ·{' '}
              {g.revoked ? '已撤回' : g.command.local_training_authorized ? '已授权' : '未授权'}
            </summary>
            <pre>{pretty(g)}</pre>
          </details>
        ))}
      </div>
      <div className="settings-card">
        <h2>数据快照（{snapshots.length}）</h2>
        {snapshots.length === 0 && <p>暂无数据快照。</p>}
        {snapshots.map((s) => (
          <article key={s.id}>
            <h3>{s.command.request_id}</h3>
            <p>
              {s.command.kind} · {s.status} · {s.examples.length} 条 · {s.source_groups} 个来源组 ·{' '}
              {s.current_evidence_valid ? '来源仍有效' : '来源已失效'}
            </p>
            <p>{s.invalidation_reasons.join('、')}</p>
            <details>
              <summary>检查来源、划分、拒绝原因与监督范围</summary>
              <pre>
                {pretty({
                  manifest: s.content_digest,
                  rejected: s.rejected,
                  examples: s.examples.map((e) => ({
                    id: e.id,
                    family: e.family,
                    origin: e.origin_group,
                    group: e.group_id,
                    split: e.split,
                    loss_message_indices: e.loss_message_indices,
                    proofs: e.proofs,
                    engineering_only: e.engineering_only,
                  })),
                })}
              </pre>
            </details>
            {(['train', 'validation'] as const).map((split) => (
              <button
                key={split}
                disabled={
                  busy ||
                  s.status !== 'ready' ||
                  !s.current_evidence_valid ||
                  !s.examples.some((e) => e.split === split)
                }
                onClick={() =>
                  void action(async () => {
                    const artifact = await feature.api.export(s.id, {
                      request_id: crypto.randomUUID(),
                      expected_content_digest: s.content_digest,
                      split,
                      purpose: split === 'train' ? 'local_training' : 'local_validation',
                    });
                    await feature.api.download(artifact.id);
                    return artifact;
                  })
                }
              >
                导出{split === 'train' ? '训练' : '验证'} JSONL
              </button>
            ))}
          </article>
        ))}
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
