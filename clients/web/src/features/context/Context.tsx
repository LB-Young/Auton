import { useEffect, useRef, useState } from 'react';
import type { ContextSnapshot, ModelInfo, Project } from '../../shared/contracts';
import type { ContextFeature } from './factory';

export function Context({ feature }: { feature: ContextFeature }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [project, setProject] = useState('');
  const [model, setModel] = useState('');
  const [goal, setGoal] = useState('');
  const [boundaries, setBoundaries] = useState('');
  const [history, setHistory] = useState('');
  const [isPublic, setPublic] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<ContextSnapshot | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    let live = true;
    Promise.all([feature.projects(), feature.models()])
      .then(([p, m]) => {
        if (!live) return;
        setProjects(p);
        setModels(m);
        setProject(p[0]?.id ?? '');
        setModel(m[0]?.id ?? '');
        setLoading(false);
      })
      .catch((e: Error) => {
        if (live) {
          setLoading(false);
          setError(e.message);
        }
      });
    return () => {
      live = false;
      generation.current++;
    };
  }, [feature]);
  function invalidate() {
    generation.current++;
    setResult(null);
    setError('');
  }
  async function assemble() {
    const current = ++generation.current;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const value = await feature.prepare(project, {
        request_id: crypto.randomUUID(),
        model_id: model,
        public: isPublic,
        state: { goal, boundaries: boundaries.split('\n').filter(Boolean), pending: [] },
        history: [
          ...history
            .split('\n')
            .filter(Boolean)
            .map((content) => ({ role: 'user' as const, content, tool_calls: [] })),
          { role: 'user', content: goal, tool_calls: [] },
        ],
      });
      if (current === generation.current) setResult(value);
    } catch (e) {
      if (current === generation.current) setError(e instanceof Error ? e.message : '装配失败');
    } finally {
      setBusy(false);
    }
  }
  async function verify() {
    if (!result) return;
    const current = ++generation.current;
    setBusy(true);
    setError('');
    try {
      const value = await feature.snapshot(project, result.id);
      if (current === generation.current) setResult(value);
    } catch (e) {
      if (current === generation.current) {
        setResult(null);
        setError(e instanceof Error ? e.message : '快照不可用');
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="module-page tool-page context-page">
      <p className="eyebrow">上下文装配 · M08</p>
      <h1>上下文</h1>
      <p className="module-description">
        先核对输入，再交给模型。查看项目来源、关键状态和剩余预算。
      </p>
      <p className="module-note">
        此页面只装配并保存快照，不调用执行模型。目标、边界与最新修订必留，预算不足时明确阻塞。
      </p>
      {loading && <p role="status">正在读取项目与模型…</p>}
      {error && (
        <p role="alert" className="notice-banner">
          {error}
        </p>
      )}
      {!loading && !projects.length && (
        <p className="notice-banner">还没有项目，请先在资产页创建项目并审核资料。</p>
      )}
      <article className="settings-card">
        <h2>装配输入</h2>
        <label className="judgment-label">
          项目
          <select
            aria-label="上下文项目"
            value={project}
            disabled={busy || loading}
            onChange={(e) => {
              invalidate();
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
          执行模型
          <select
            aria-label="上下文模型"
            value={model}
            disabled={busy || loading}
            onChange={(e) => {
              invalidate();
              setModel(e.target.value);
            }}
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
              </option>
            ))}
          </select>
        </label>
        <label className="judgment-label">
          当前目标
          <textarea
            className="judgment-input"
            rows={3}
            aria-label="上下文目标"
            value={goal}
            maxLength={4000}
            disabled={busy}
            onChange={(e) => {
              invalidate();
              setGoal(e.target.value);
            }}
          />
        </label>
        <label className="judgment-label">
          必须保留的边界（每行一条，最多 20 条，每条 300 字）
          <textarea
            className="judgment-input"
            rows={3}
            aria-label="上下文边界"
            value={boundaries}
            disabled={busy}
            onChange={(e) => {
              invalidate();
              setBoundaries(e.target.value);
            }}
          />
        </label>
        <label className="judgment-label">
          旧用户轮次（每行一轮，最多 299 轮）
          <textarea
            className="judgment-input"
            rows={4}
            aria-label="上下文历史"
            value={history}
            disabled={busy}
            onChange={(e) => {
              invalidate();
              setHistory(e.target.value);
            }}
          />
        </label>
        <label className="judgment-check">
          <input
            type="checkbox"
            checked={isPublic}
            disabled={busy}
            onChange={(e) => {
              invalidate();
              setPublic(e.target.checked);
            }}
          />
          确认本次输入及项目资料均可公开，用于远程模型准入检查
        </label>
        <button
          className="secondary-button"
          disabled={busy || loading || !project || !model || !goal.trim()}
          onClick={() => void assemble()}
        >
          {busy ? '正在处理…' : '装配上下文'}
        </button>
      </article>
      {result && (
        <article className="settings-card context-result" role="status">
          <h2>{result.status === 'ready' ? '上下文已就绪' : '上下文已阻塞'}</h2>
          {result.reasons.length > 0 && (
            <p className="notice-banner">原因：{result.reasons.join('、')}</p>
          )}
          <dl>
            <div>
              <dt>计数来源</dt>
              <dd>
                {result.counter_source === 'official-local'
                  ? '官方本地 tokenizer'
                  : result.counter_source === 'test-fixture'
                    ? '测试计数 · 非真实 tokenizer'
                    : '计数不可用'}
              </dd>
            </div>
            <div>
              <dt>本地输入计数</dt>
              <dd>{result.input_tokens ?? '不可用'}</dd>
            </div>
            <div>
              <dt>保守准入预算</dt>
              <dd>
                {result.admission_tokens ?? '不可用'} / {result.context_limit}
              </dd>
            </div>
            <div>
              <dt>预留输出 / 剩余</dt>
              <dd>
                {result.output_reserved} / {result.remaining_tokens ?? '不可用'}
              </dd>
            </div>
            <div>
              <dt>保留状态</dt>
              <dd>
                目标修订 {result.goal_revision} · 截止点 {result.state_cutoff} · 未修改 checkpoint
              </dd>
            </div>
            <div>
              <dt>压缩说明</dt>
              <dd>
                移除 {result.dropped_history_groups} 个完整旧轮次，排除{' '}
                {result.excluded_evidence.length} 个证据块
              </dd>
            </div>
          </dl>
          <p className="module-note">
            本地计数对应固定模板；远程服务的实际用量以响应 usage
            为准。当前保守准入仍保留字节预算保护。
          </p>
          <h3>检索来源</h3>
          {!result.evidence.length && <p>没有保留匹配证据。项目说明和关键状态仍参与装配。</p>}
          {result.evidence.map((e) => (
            <details key={e.content_digest}>
              <summary>{e.asset_ids.join('、')} · 不可信证据</summary>
              {e.locations.map((l, i) => (
                <p key={i}>
                  {l.asset_id} · {l.source} · 字符 [{l.start_character}, {l.end_character})
                </p>
              ))}
              <pre className="tool-output">{e.text}</pre>
              <p className="context-hash">SHA256 {e.content_digest}</p>
            </details>
          ))}
          <details>
            <summary>高级视图：完整输入与版本</summary>
            <pre className="tool-output">{JSON.stringify(result, null, 2)}</pre>
          </details>
          <button className="secondary-button" disabled={busy} onClick={() => void verify()}>
            重新校验快照
          </button>
        </article>
      )}
    </section>
  );
}
