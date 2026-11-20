import { ArrowUp, SlidersHorizontal, Sparkles } from 'lucide-react';
import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
  type CSSProperties,
} from 'react';
import type { AgentRun, RunCommand } from '../../shared/contracts';
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
  renderArtifact,
  onNavigate,
}: {
  feature: AgentFeature;
  onNavigate?: (view: 'genome' | 'tools') => void;
  renderArtifact?: (text: string) => ReactNode;
  renderTrajectory?: (run: AgentRun, onRecovered: (run: AgentRun) => void) => ReactNode;
}) {
  const controller = feature.controller;
  const {
    draftVersion,
    projects,
    workspaces,
    models,
    project,
    runs,
    run,
    loading,
    busy,
    error,
    connected,
    progress,
    next,
    search,
  } = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [workspace, setWorkspace] = useState(feature.draft.workspace);
  const [model, setModel] = useState(feature.draft.model);
  const [goal, setGoal] = useState(feature.draft.goal);
  const goalInput = useRef<HTMLTextAreaElement>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [boundaries, setBoundaries] = useState(feature.draft.boundaries);
  const [kind, setKind] = useState<'research' | 'file'>(feature.draft.kind);
  const [path, setPath] = useState(feature.draft.path);
  const [content, setContent] = useState(feature.draft.content);
  const [isPublic, setPublic] = useState(feature.draft.isPublic);
  useEffect(() => {
    Object.assign(feature.draft, {
      workspace,
      model,
      goal,
      boundaries,
      kind,
      path,
      content,
      isPublic,
    });
  }, [feature, workspace, model, goal, boundaries, kind, path, content, isPublic]);
  const draftRevision = useRef(draftVersion);
  useEffect(() => {
    if (draftRevision.current !== draftVersion) {
      draftRevision.current = draftVersion;
      setGoal(feature.draft.goal);
      setContent(feature.draft.content);
      setBoundaries(feature.draft.boundaries);
      setKind(feature.draft.kind);
      setPath(feature.draft.path);
      setPublic(feature.draft.isPublic);
      setSettingsOpen(false);
    }
  }, [draftVersion, feature]);
  useEffect(() => {
    if (run || (draftVersion === 0 && new URL(window.location.href).searchParams.has('run')))
      return;
    const frame = requestAnimationFrame(() => {
      goalInput.current?.focus({ preventScroll: true });
      goalInput.current?.scrollIntoView({ block: 'center' });
    });
    return () => cancelAnimationFrame(frame);
  }, [draftVersion, run]);
  const [previewWidth, setPreviewWidth] = useState(460);
  const [revision, setRevision] = useState('');
  const [feedbackNote, setFeedbackNote] = useState('');
  const [feedbackMessage, setFeedbackMessage] = useState('');
  const [preview, setPreview] = useState<{ title: string; text: string; url: string } | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewScope = useRef(0);
  const reading = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const opener = useRef<HTMLElement | null>(null);
  const previewPanel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (preview) previewPanel.current?.focus();
  }, [preview]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        previewScope.current++;
        setPreview(null);
        setPreviewLoading(false);
        setPreviewError('');
        opener.current?.focus();
      }
    };
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, []);
  const running = run && !terminal.has(run.status);
  useEffect(() => {
    void controller.start();
    return () => controller.dispose();
  }, [controller]);
  useEffect(() => {
    const changed = () => {
      void controller.start();
    };
    window.addEventListener('popstate', changed);
    return () => window.removeEventListener('popstate', changed);
  }, [controller]);
  useEffect(() => {
    if (!workspace && workspaces[0]) setWorkspace(workspaces[0].id);
    if (!model && models[0]) setModel(models[0].id);
  }, [workspace, model, workspaces, models]);
  useEffect(() => {
    previewScope.current++;
    setPreview(null);
    setPreviewError('');
    setPreviewLoading(false);
    setFeedbackMessage('');
    follow.current = true;
  }, [run?.id]);
  useEffect(() => {
    if (follow.current && reading.current) reading.current.scrollTop = reading.current.scrollHeight;
  }, [run?.version, progress?.sequence]);
  async function openPreview(title: string, url: string) {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const current = ++previewScope.current;
    setPreview(null);
    setPreviewError('');
    setPreviewLoading(true);
    try {
      const text = await feature.preview(url);
      if (current === previewScope.current) setPreview({ title, text, url });
    } catch (error) {
      if (current === previewScope.current)
        setPreviewError(error instanceof Error ? error.message : '产物不可用');
    } finally {
      if (current === previewScope.current) setPreviewLoading(false);
    }
  }
  const act = (action: () => Promise<AgentRun>) => controller.act(action);
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
        expected_version: selected.version,
        action,
        goal: action === 'revise' ? revision : null,
      }),
    );
  }
  return (
    <section className="module-page tool-page context-page agent-page">
      <header className="task-intro" hidden={Boolean(run)}>
        <span className="task-intro-icon" aria-hidden="true">
          <Sparkles size={32} strokeWidth={1.5} />
        </span>
        <p className="eyebrow">从一个想法开始</p>
        <h1>开始一件值得完成的事</h1>
        <p className="module-description">描述你想完成的任务，让我们一起推进。</p>
      </header>
      {loading && <p role="status">正在加载任务连接…</p>}
      {error && (
        <p className="notice-banner" role="alert">
          {error}
        </p>
      )}
      <article className="task-compose-area" aria-label="任务对话输入">
        <div className="composer task-chat-composer">
          <label className="task-goal-label">
            <span className="task-sr-only">你想完成什么？</span>
            <textarea
              ref={goalInput}
              className="task-composer"
              aria-label="真实任务目标"
              placeholder="给 Auton 发消息，描述你想完成的任务…"
              rows={3}
              maxLength={2000}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              onKeyDown={(event) => {
                if (
                  event.key === 'Enter' &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing &&
                  event.keyCode !== 229
                ) {
                  event.preventDefault();
                  if (!busy && !loading && project && workspace && model && goal.trim())
                    void create();
                }
              }}
            />
          </label>
          <div className="task-chat-toolbar">
            <button
              type="button"
              className="task-settings-toggle"
              aria-expanded={settingsOpen}
              aria-controls="task-settings"
              onClick={() => setSettingsOpen(!settingsOpen)}
            >
              <SlidersHorizontal size={16} />
              任务设置
            </button>
            <span className="task-model-label">{model || '加载模型…'}</span>
            <button
              className="task-send"
              aria-label="启动真实任务"
              title="发送任务（Enter）"
              disabled={busy || loading || !project || !workspace || !model || !goal.trim()}
              onClick={() => void create()}
            >
              <ArrowUp size={21} />
            </button>
          </div>
        </div>
        <p className="task-composer-hint">
          {!loading && (!projects.length || !workspaces.length) ? (
            <>
              首次使用，请在
              <button type="button" onClick={() => setSettingsOpen(true)}>
                任务设置
              </button>
              中准备项目和工作区。可以先写下你的想法。
            </>
          ) : (
            'Enter 发送 · Shift + Enter 换行'
          )}
        </p>
        <div id="task-settings" className="task-settings" hidden={!settingsOpen}>
          <h2>任务设置</h2>
          {!loading && (!projects.length || !workspaces.length) && (
            <div className="task-setup" role="status">
              <p>可以先输入任务目标。开始执行前，请准备项目资料和工作区。</p>
              {!projects.length && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onNavigate?.('genome')}
                >
                  创建项目与添加资料
                </button>
              )}
              {!workspaces.length && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onNavigate?.('tools')}
                >
                  创建工作区
                </button>
              )}
            </div>
          )}
          <div className="run-config-grid">
            <label className="judgment-label">
              项目
              <select
                aria-label="任务项目"
                value={project}
                disabled={busy}
                onChange={(e) => void controller.project(e.target.value)}
              >
                {!projects.length && <option value="">请先创建项目</option>}
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
                {!workspaces.length && <option value="">请先创建工作区</option>}
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
                {models.some((m) => m.provider === 'local') && (
                  <option value="project_default">项目批准的灰度策略</option>
                )}
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
          </div>
          <details>
            <summary>任务边界（可选）</summary>
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
          </details>
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
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setPublic(e.target.checked)}
            />
            确认任务、项目资料及工作区内容均可发送给所选远程模型
          </label>
        </div>
      </article>
      <details className="task-history">
        <summary>项目会话与任务</summary>
        <article className="settings-card">
          <h2>项目会话与任务</h2>
          <label className="judgment-label">
            搜索项目任务
            <input
              aria-label="搜索项目任务"
              maxLength={100}
              value={search}
              onChange={(event) => void controller.search(event.target.value)}
            />
          </label>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => {
              controller.newRun();
              setGoal('');
              setContent('');
            }}
          >
            新建任务会话
          </button>
          {!runs.length && (
            <p>{next !== null ? '本页暂无匹配任务，可以继续加载。' : '当前没有匹配任务'}</p>
          )}
          {runs.map((r) => (
            <button
              key={r.id}
              className="secondary-button"
              disabled={busy}
              onClick={() => void controller.select(r.id)}
            >
              {r.command.goal.slice(0, 30)} · {statusLabels[r.status]}
            </button>
          ))}
          {next !== null && (
            <button
              className="secondary-button"
              disabled={loading}
              onClick={() => void controller.more()}
            >
              加载更多任务
            </button>
          )}
        </article>
      </details>
      {run && (
        <article className="settings-card agent-result" aria-label="真实任务执行记录">
          <h2>执行记录</h2>
          <p>
            任务会话 {run.id.slice(0, 12)} · {run.command.goal.slice(0, 100)}
          </p>
          <button className="secondary-button" onClick={() => void controller.select(run.id)}>
            刷新任务状态
          </button>
          {previewLoading && <p role="status">正在读取授权产物…</p>}
          {previewError && <p role="alert">{previewError}</p>}
          {preview && (
            <aside
              ref={previewPanel}
              tabIndex={-1}
              style={{ '--run-panel-width': `${previewWidth}px` } as CSSProperties}
              className="run-artifact-panel"
              aria-label="真实产物预览"
            >
              <header>
                <strong>{preview.title}</strong>
                <button
                  className="secondary-button"
                  onClick={() => {
                    previewScope.current++;
                    setPreview(null);
                    opener.current?.focus();
                  }}
                >
                  关闭产物预览
                </button>
              </header>
              <p>只读预览 · 来自授权接口</p>
              <label className="judgment-label">
                面板宽度
                <input
                  aria-label="产物面板宽度"
                  type="range"
                  min={320}
                  max={720}
                  step={20}
                  value={previewWidth}
                  onChange={(event) => setPreviewWidth(Number(event.target.value))}
                />
              </label>
              {renderArtifact?.(preview.text) ?? <Markdown>{preview.text}</Markdown>}
              <a href={preview.url} download>
                下载此产物
              </a>
            </aside>
          )}
          {!connected && <p role="note">事件连接正在恢复；服务端任务继续运行，重连只读取状态。</p>}
          {progress &&
            progress.version === run.version &&
            progress.goal_revision === run.goal_revision &&
            progress.request_id === run.model_request_id &&
            run.status === 'running' && (
              <div aria-label="临时生成内容">
                <p>正在生成 · 临时内容，尚未保存</p>
                <Markdown>{progress.text}</Markdown>
              </div>
            )}
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
              <p>批准绑定当前目标与检查点；状态变化或审批到期后需重新核对。</p>
              <label className="judgment-label">
                拒绝原因（可选）
                <textarea
                  aria-label="审批拒绝原因"
                  value={feedbackNote}
                  maxLength={2000}
                  onChange={(event) => setFeedbackNote(event.target.value)}
                />
              </label>
              <button
                className="secondary-button"
                disabled={busy}
                onClick={() => {
                  const selected = run;
                  void act(async () => {
                    await feature.feedback(selected.id, {
                      request_id: crypto.randomUUID(),
                      expected_goal_revision: selected.goal_revision,
                      checkpoint_version: selected.version,
                      rating: 'unhelpful',
                      category: 'approval',
                      note: feedbackNote,
                    });
                    return feature.command(selected.id, {
                      request_id: crypto.randomUUID(),
                      expected_goal_revision: selected.goal_revision,
                      expected_version: selected.version,
                      action: 'cancel',
                      goal: null,
                    });
                  });
                }}
              >
                拒绝并停止任务
              </button>
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
          <div
            className="run-reading"
            ref={reading}
            tabIndex={0}
            aria-label="任务消息"
            onScroll={() => {
              const node = reading.current;
              if (node)
                follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
            }}
          >
            {run.history
              .filter((m) => m.role !== 'tool')
              .map((m, i) => (
                <div className="agent-message" key={i}>
                  <strong>{m.role === 'user' ? '你' : 'Agent'}</strong>
                  <Markdown>{m.content ?? '请求受控工具'}</Markdown>
                </div>
              ))}
          </div>
          <button
            className="secondary-button"
            onClick={() => {
              follow.current = true;
              reading.current?.scrollTo({ top: reading.current.scrollHeight, behavior: 'smooth' });
            }}
          >
            查看最新消息
          </button>
          {run.receipts.map((r) => (
            <details key={r.operation_id}>
              <summary>
                {r.tool} · {r.outcome} · {r.code}
              </summary>
              <pre className="tool-output">{r.output}</pre>
              <p>{r.evidence}</p>
              {r.artifact && (
                <button
                  className="secondary-button"
                  onClick={() =>
                    void openPreview(
                      r.artifact!.path,
                      `/api/v1/tools/operations/${encodeURIComponent(r.operation_id)}/artifact`,
                    )
                  }
                >
                  预览任务文件 {r.artifact.path}
                </button>
              )}
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
            <button
              className="secondary-button"
              onClick={() =>
                void openPreview(
                  '任务报告',
                  `/api/v1/agent/runs/${encodeURIComponent(run.id)}/report`,
                )
              }
            >
              预览任务报告
            </button>
          )}
          {run.final_text && (
            <a href={`/api/v1/agent/runs/${encodeURIComponent(run.id)}/report`} download>
              下载任务报告
            </a>
          )}
          {terminal.has(run.status) && (
            <div className="feedback-card">
              <label className="judgment-label">
                交付反馈
                <textarea
                  aria-label="任务反馈说明"
                  maxLength={2000}
                  value={feedbackNote}
                  onChange={(event) => setFeedbackNote(event.target.value)}
                />
              </label>
              {(['helpful', 'unhelpful'] as const).map((rating) => (
                <button
                  className="secondary-button"
                  key={rating}
                  onClick={() => {
                    const selected = run.id;
                    void feature
                      .feedback(run.id, {
                        request_id: crypto.randomUUID(),
                        expected_goal_revision: run.goal_revision,
                        checkpoint_version: run.version,
                        rating,
                        category: 'delivery',
                        note: feedbackNote,
                      })
                      .then(() => {
                        if (controller.getSnapshot().run?.id === selected)
                          setFeedbackMessage('反馈已保存 · 用户标签，尚未独立核验');
                      })
                      .catch((error: Error) => {
                        if (controller.getSnapshot().run?.id === selected)
                          setFeedbackMessage(error.message);
                      });
                  }}
                >
                  {rating === 'helpful' ? '有帮助' : '需要改进'}
                </button>
              ))}
              {feedbackMessage && <p role="note">{feedbackMessage}</p>}
            </div>
          )}
          {renderTrajectory?.(run, controller.accept)}
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
