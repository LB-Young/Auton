import './workspace.css';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import {
  ArrowUp,
  Check,
  Copy,
  Download,
  FileText,
  Folder,
  Menu,
  MessageSquare,
  Moon,
  PanelRight,
  Plus,
  Sparkles,
  Square,
  Sun,
  X,
} from 'lucide-react';
import { Markdown } from '../../shared/Markdown';
import type { AgentRun } from '../../shared/contracts';
import { finished } from './controller';
import type { ConversationFeature } from './factory';
import { ProjectPicker } from './ProjectPicker';

const statuses: Record<AgentRun['status'], string> = {
  queued: '等待执行',
  running: '正在处理',
  waiting_approval: '需要你的确认',
  blocked: '需要处理',
  pausing: '正在暂停',
  paused: '已暂停',
  cancelling: '正在停止',
  cancelled: '已停止',
  succeeded: '已回复',
  failed: '未完成',
};
function reason(run: AgentRun) {
  if (run.reason.includes('critical_context_limit') || run.reason === 'context_limit')
    return '本轮文件和工具记录超过上下文上限，已读取的记录仍然保留。可缩小读取范围；更新后端预算后，请停止此轮并重新发送任务，旧任务的预算不会自动改变。';
  if (run.reason === 'model_output_incomplete')
    return '模型输出达到单次长度上限，本轮尚未完成。请停止此轮，将较大的代码修改拆成小步骤后重新发送。';
  if (run.reason === 'run_step_or_tool_limit' || run.reason === 'run_tool_limit')
    return '本轮达到执行步数或工具调用上限。请停止此轮，再继续一个范围更明确的任务。';
  if (run.reason === 'tool_result_too_large')
    return '读取结果过大。请停止此轮，并要求按行分段读取相关文件后继续分析。';
  if (run.reason.includes('data_egress_denied'))
    return '当前任务未允许发送给远程模型。请停止这一轮，再选择合适的模型发送。';
  if (run.reason.includes('model_unavailable') || run.reason.includes('credential'))
    return '模型暂不可用，请检查后端模型配置及 API key。';
  if (run.reason.includes('budget'))
    return '本轮已达到运行预算，需要停止后开始新的一轮，或由后端调整预算。';
  if (run.reason.includes('interrupted') || run.reason.includes('shutdown'))
    return '服务重启中断了本轮任务，可在工作面板恢复。';
  return '本轮任务暂时无法继续，请在工作面板查看详细状态。';
}

export function ConversationWorkspace({ feature }: { feature: ConversationFeature }) {
  const controller = feature.controller;
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [panel, setPanel] = useState(false);
  const [projectPicker, setProjectPicker] = useState(false);
  const [sidebar, setSidebar] = useState(false);
  const [search, setSearch] = useState('');
  const [theme, setTheme] = useState(() => localStorage.getItem('auton.theme') ?? 'light');
  const [preview, setPreview] = useState<{ title: string; text: string } | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [historyNotice, setHistoryNotice] = useState<{
    path: string;
    text: string;
    copied: boolean;
  } | null>(null);
  const historyEpoch = useRef(0);
  const input = useRef<HTMLTextAreaElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const previewEpoch = useRef(0);
  const opened = useRef('');
  const current = state.current;
  const run = current?.turns.at(-1);
  const active = Boolean(run && !finished(run));
  const model = state.models.find((m) => m.id === state.model);
  const panelRef = useRef<HTMLElement>(null);
  const panelToggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    void controller.start();
    return () => controller.dispose();
  }, [controller]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('auton.theme', theme);
  }, [theme]);
  useEffect(() => {
    const pop = () => {
      const id = new URL(window.location.href).searchParams.get('conversation');
      if (id) void controller.select(id);
      else controller.newConversation();
    };
    const keys = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'n') {
        event.preventDefault();
        controller.newConversation();
        setSidebar(false);
        input.current?.focus();
      }
      if (event.key === 'Escape') {
        setSidebar(false);
        setPanel(false);
        panelToggle.current?.focus();
      }
    };
    window.addEventListener('popstate', pop);
    document.addEventListener('keydown', keys);
    return () => {
      window.removeEventListener('popstate', pop);
      document.removeEventListener('keydown', keys);
    };
  }, [controller]);
  useEffect(() => {
    input.current?.focus();
    follow.current = true;
    previewEpoch.current++;
    setPreview(null);
    setPreviewError('');
    setPreviewLoading(false);
    historyEpoch.current++;
    setHistoryBusy(false);
    setHistoryNotice(null);
  }, [current?.conversation.id]);
  useEffect(() => {
    if (follow.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [run?.version, state.progress?.sequence, current?.conversation.id]);
  useEffect(() => {
    if (!run || !['waiting_approval', 'blocked', 'paused'].includes(run.status)) return;
    const key = `${run.id}:${run.status}`;
    if (opened.current !== key) {
      opened.current = key;
      setPanel(true);
    }
  }, [run?.id, run?.status, run]);
  useEffect(() => {
    if (panel) panelRef.current?.focus({ preventScroll: true });
  }, [panel]);
  async function send() {
    follow.current = true;
    await controller.send();
    input.current?.focus();
  }
  async function copyHistoryPath() {
    if (!current?.turns.length || historyBusy) return;
    const epoch = ++historyEpoch.current;
    setHistoryBusy(true);
    setHistoryNotice(null);
    const record = feature.historyPath(current.conversation.id);
    try {
      if (navigator.clipboard?.write && typeof ClipboardItem !== 'undefined') {
        // Invoke the clipboard API during the click gesture, including on Safari.
        const text = record.then((value) => {
          if (epoch !== historyEpoch.current) throw new Error('会话已切换');
          return new Blob([value.path], { type: 'text/plain' });
        });
        await navigator.clipboard.write([new ClipboardItem({ 'text/plain': text })]);
      } else {
        const value = await record;
        if (epoch !== historyEpoch.current) return;
        if (!navigator.clipboard?.writeText) throw new Error('浏览器无法自动复制');
        await navigator.clipboard.writeText(value.path);
      }
      const value = await record;
      if (epoch === historyEpoch.current)
        setHistoryNotice({
          path: value.path,
          copied: true,
          text: '已复制会话记录路径（当前快照）',
        });
    } catch {
      try {
        const value = await record;
        if (epoch === historyEpoch.current)
          setHistoryNotice({
            path: value.path,
            copied: false,
            text: '会话记录已保存，浏览器未允许自动复制。点击下方路径后手动复制。',
          });
      } catch (error) {
        if (epoch === historyEpoch.current)
          setHistoryNotice({
            path: '',
            copied: false,
            text: error instanceof Error ? error.message : '导出会话记录失败，请重试',
          });
      }
    } finally {
      if (epoch === historyEpoch.current) setHistoryBusy(false);
    }
  }
  async function openArtifact(title: string, url: string) {
    const epoch = ++previewEpoch.current;
    setPanel(true);
    setPreview(null);
    setPreviewLoading(true);
    setPreviewError('');
    try {
      const text = await feature.artifact(url);
      if (epoch === previewEpoch.current) setPreview({ title, text });
    } catch (error) {
      if (epoch === previewEpoch.current)
        setPreviewError(error instanceof Error ? error.message : '文件暂不可用');
    } finally {
      if (epoch === previewEpoch.current) setPreviewLoading(false);
    }
  }
  function newConversation() {
    controller.newConversation();
    setSidebar(false);
    setPanel(false);
    input.current?.focus();
  }
  return (
    <div className={`cw-app ${panel ? 'cw-with-panel' : ''}`}>
      {projectPicker && (
        <ProjectPicker
          feature={feature}
          initial={state.projectPath}
          hasConversation={Boolean(current)}
          onClose={() => {
            setProjectPicker(false);
            input.current?.focus();
          }}
          onSelect={(path) => {
            controller.project(path);
            setProjectPicker(false);
            setPanel(false);
            input.current?.focus();
          }}
        />
      )}
      {sidebar && (
        <button
          className="cw-overlay"
          aria-label="关闭历史导航遮罩"
          onClick={() => setSidebar(false)}
        />
      )}
      <aside className={`cw-sidebar ${sidebar ? 'cw-sidebar-open' : ''}`} aria-label="历史对话">
        <div className="cw-brand">
          <Sparkles size={25} />
          <strong>
            Auton<span>.</span>
          </strong>
          <button
            className="cw-icon cw-mobile-only"
            aria-label="关闭历史对话"
            onClick={() => setSidebar(false)}
          >
            <X size={18} />
          </button>
        </div>
        <button className="cw-new" onClick={newConversation} disabled={state.busy || state.loading}>
          <Plus size={17} />
          新对话<span>⌘ N</span>
        </button>
        <input
          className="cw-search"
          aria-label="搜索历史对话"
          placeholder="搜索对话…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <p className="cw-section-label">对话记录</p>
        <nav className="cw-history">
          {state.conversations
            .filter((c) => c.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()))
            .map((c) => (
              <button
                key={c.id}
                className={current?.conversation.id === c.id ? 'selected' : ''}
                aria-current={current?.conversation.id === c.id ? 'page' : undefined}
                disabled={state.busy}
                onClick={() => {
                  void controller.select(c.id);
                  setSidebar(false);
                }}
              >
                <MessageSquare size={16} />
                <span>{c.title}</span>
              </button>
            ))}
          {!state.loading && !state.conversations.length && (
            <p className="cw-empty-history">新的想法与进展，都会留在这里。</p>
          )}
        </nav>
        <div className="cw-sidebar-footer">
          <span className="cw-dot" />
          个人工作区
        </div>
      </aside>
      <main className="cw-main">
        <header className="cw-header">
          <button
            className="cw-icon cw-mobile-only"
            aria-label="打开历史对话"
            onClick={() => setSidebar(true)}
          >
            <Menu size={20} />
          </button>
          <span className="cw-title">{current?.conversation.title ?? '新对话'}</span>
          <button
            className="cw-icon"
            aria-label="复制会话记录路径"
            title={
              current?.turns.length
                ? '导出当前会话 JSON 快照并复制记录路径'
                : '发送首条消息后可复制会话记录路径'
            }
            disabled={!current?.turns.length || state.loading || state.busy || historyBusy}
            onClick={() => void copyHistoryPath()}
          >
            {historyNotice?.copied ? <Check size={19} /> : <Copy size={19} />}
          </button>
          <button
            className="cw-icon"
            aria-label="切换主题"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
          </button>
          <button
            ref={panelToggle}
            className={`cw-icon ${panel ? 'selected' : ''}`}
            aria-label={panel ? '收起工作面板' : '展开工作面板'}
            aria-expanded={panel}
            aria-controls="conversation-work-panel"
            onClick={() => setPanel(!panel)}
          >
            <PanelRight size={20} />
          </button>
        </header>
        {historyNotice && (
          <div className="cw-history-toast">
            <div>
              <p role="status">{historyNotice.text}</p>
              <button
                className="cw-icon"
                aria-label="关闭记录路径提示"
                onClick={() => setHistoryNotice(null)}
              >
                <X size={16} />
              </button>
            </div>
            {historyNotice.path && (
              <input
                aria-label="会话记录路径"
                readOnly
                value={historyNotice.path}
                onFocus={(e) => e.currentTarget.select()}
              />
            )}
          </div>
        )}
        <div
          ref={scroll}
          className="cw-messages"
          aria-label="对话消息"
          onScroll={() => {
            const node = scroll.current;
            if (node) follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 100;
          }}
        >
          {!current?.turns.length ? (
            <section className="cw-welcome">
              <div className="cw-welcome-mark">
                <Sparkles size={34} strokeWidth={1.5} />
              </div>
              <p>从一个想法开始</p>
              <h1>今天，想一起完成什么？</h1>
              <span>提问、讨论，或把一件事情交给 Auton。</span>
            </section>
          ) : (
            <div className="cw-thread">
              {current.turns.map((turn) => (
                <div className="cw-turn" key={turn.id}>
                  <article className="cw-user" aria-label="用户消息">
                    <p>{turn.command.goal}</p>
                  </article>
                  <article className="cw-assistant" aria-label="助手消息">
                    <span className="cw-assistant-mark">
                      <Sparkles size={19} />
                    </span>
                    <div className="cw-response">
                      {turn.final_text ? (
                        <Markdown>{turn.final_text}</Markdown>
                      ) : turn.id === run?.id &&
                        state.progress?.version === turn.version &&
                        state.progress.request_id === turn.model_request_id &&
                        state.progress.text ? (
                        <Markdown>{state.progress.text}</Markdown>
                      ) : (
                        <p className="cw-status" role="status">
                          {statuses[turn.status]}
                          {turn.status === 'running' || turn.status === 'queued' ? '…' : ''}
                        </p>
                      )}
                      {['blocked', 'paused', 'failed'].includes(turn.status) && (
                        <p className="cw-turn-notice">{reason(turn)}</p>
                      )}
                      {turn.status === 'waiting_approval' && (
                        <button className="cw-inline-action" onClick={() => setPanel(true)}>
                          有操作需要确认，打开工作面板
                        </button>
                      )}
                      <span className="cw-message-meta">
                        {turn.resolved_model_id || turn.command.model_id}
                        {turn.source === 'test' ? ' · 测试替身' : ''}
                        {finished(turn) ? ` · ${statuses[turn.status]}` : ''}
                      </span>
                    </div>
                  </article>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="cw-compose-area">
          {state.error && (
            <div className="cw-error" role="alert">
              {state.error}
              <button
                onClick={() =>
                  current
                    ? void controller.select(current.conversation.id)
                    : void controller.start()
                }
                disabled={state.busy}
              >
                重新加载
              </button>
            </div>
          )}
          <div className="cw-composer">
            <textarea
              ref={input}
              aria-label="对话输入"
              rows={3}
              maxLength={4000}
              placeholder="给 Auton 发消息…"
              value={state.draft}
              disabled={state.busy || state.loading}
              onChange={(e) => controller.draft(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === 'Enter' &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing &&
                  e.keyCode !== 229
                ) {
                  e.preventDefault();
                  if (!active) void send();
                }
              }}
            />
            {state.projectPath && (
              <div className="cw-project-chip" title={state.projectPath}>
                <Folder size={14} />
                <span>{state.projectPath.split('/').at(-1)}</span>
                <button
                  type="button"
                  aria-label="切回普通对话"
                  disabled={state.busy || state.loading}
                  onClick={() => {
                    controller.project(null);
                    setPanel(false);
                  }}
                >
                  <X size={13} />
                </button>
              </div>
            )}
            <div className="cw-composer-toolbar">
              <button
                type="button"
                className="cw-icon cw-project-button"
                aria-label="选择项目目录"
                title="选择本地项目目录"
                disabled={state.busy || state.loading}
                onClick={() => setProjectPicker(true)}
              >
                <Folder size={18} />
              </button>
              <Sparkles size={15} />
              <select
                aria-label="选择模型"
                value={state.model}
                disabled={state.busy || state.loading}
                onChange={(e) => controller.model(e.target.value)}
              >
                {!state.models.length && (
                  <option value="">{state.loading ? '正在加载模型…' : '暂无可用模型'}</option>
                )}
                {state.models.map((m) => (
                  <option
                    key={m.id}
                    value={m.id}
                    disabled={m.health === 'unavailable' || m.health === 'credential_missing'}
                  >
                    {m.location === 'remote' ? '远程 API' : '本地'} · {m.id}
                    {m.location === 'local'
                      ? ` · ${m.adapter_revision ?? m.declared_revision}`
                      : ''}
                    {m.health === 'credential_missing'
                      ? '（缺少密钥）'
                      : m.health === 'unavailable'
                        ? '（不可用）'
                        : ''}
                  </option>
                ))}
              </select>
              {active ? (
                <button
                  className="cw-send cw-stop"
                  aria-label="停止当前任务"
                  disabled={state.busy || run?.status === 'cancelling'}
                  onClick={() => void controller.command('cancel')}
                >
                  <Square size={15} fill="currentColor" />
                </button>
              ) : (
                <button
                  className="cw-send"
                  aria-label="发送消息"
                  disabled={
                    state.busy ||
                    state.loading ||
                    !state.draft.trim() ||
                    !model ||
                    ['unavailable', 'credential_missing'].includes(model.health)
                  }
                  onClick={() => void send()}
                >
                  <ArrowUp size={20} />
                </button>
              )}
            </div>
          </div>
          <p className="cw-caption">
            {state.loading
              ? '正在连接工作区…'
              : model?.location === 'remote'
                ? `处理时，消息、对话历史及本会话读取的文件将发送给 ${model.provider}。`
                : '当前使用本地模型处理对话。'}{' '}
            <span>Shift + Enter 换行</span>
          </p>
        </div>
      </main>
      {panel && (
        <aside
          ref={panelRef}
          tabIndex={-1}
          id="conversation-work-panel"
          className="cw-panel"
          aria-label="工作面板"
        >
          <header>
            <strong>工作面板</strong>
            <button
              className="cw-icon"
              aria-label="关闭工作面板"
              onClick={() => {
                setPanel(false);
                panelToggle.current?.focus();
              }}
            >
              <X size={19} />
            </button>
          </header>
          <div className="cw-panel-body">
            {state.projectPath && (
              <section>
                <h2>当前项目</h2>
                <div className="cw-project-location">
                  <Folder size={15} />
                  <span>{state.projectPath}</span>
                </div>
              </section>
            )}

            {!run ? (
              <div className="cw-panel-empty">
                <FileText size={28} />
                <h2>随任务展开</h2>
                <p>任务进度、操作确认和生成的文件会显示在这里。</p>
              </div>
            ) : (
              <>
                <section>
                  <h2>当前进度</h2>

                  <p className="cw-run-status" role="status">
                    {statuses[run.status]}
                  </p>
                  {['blocked', 'paused', 'failed'].includes(run.status) && <p>{reason(run)}</p>}
                  <details>
                    <summary>运行详情</summary>
                    <p className="cw-technical">{run.reason}</p>
                    <p>
                      {run.steps} 步 · {run.tokens_used} tokens · $
                      {(run.cost_microusd / 1000000).toFixed(6)}
                    </p>
                    <p>模型：{run.resolved_model_id || run.command.model_id}</p>
                  </details>
                  {run.status === 'waiting_approval' && (
                    <div className="cw-approval">
                      <p>以下操作需要你确认，批准仅对当前操作有效。</p>
                      {run.plans
                        .filter(
                          (p) =>
                            !run.receipts.some((r) => r.operation_id === p.operation_id) &&
                            !run.approvals[p.operation_id],
                        )
                        .map((p) => (
                          <div key={p.operation_id}>
                            <strong>{p.title}</strong>
                            <pre>{p.preview}</pre>
                          </div>
                        ))}
                      <button
                        className="cw-primary"
                        disabled={state.busy}
                        onClick={() => void controller.command('approve')}
                      >
                        批准本次操作
                      </button>
                      <button
                        className="cw-secondary"
                        disabled={state.busy}
                        onClick={() => void controller.command('cancel')}
                      >
                        拒绝并停止
                      </button>
                    </div>
                  )}
                  {run.status === 'blocked' && run.reason === 'tool_outcome_unknown' && (
                    <button
                      className="cw-secondary"
                      disabled={state.busy}
                      onClick={() => void controller.command('reconcile')}
                    >
                      核对操作结果
                    </button>
                  )}
                  {['blocked', 'paused'].includes(run.status) && (
                    <button
                      className="cw-secondary"
                      disabled={state.busy}
                      onClick={() => void controller.command('resume')}
                    >
                      恢复任务
                    </button>
                  )}
                  {run.status === 'running' && (
                    <button
                      className="cw-secondary"
                      disabled={state.busy}
                      onClick={() => void controller.command('pause')}
                    >
                      暂停任务
                    </button>
                  )}
                  {!finished(run) && (
                    <button
                      className="cw-secondary"
                      disabled={state.busy || run.status === 'cancelling'}
                      onClick={() => void controller.command('cancel')}
                    >
                      停止任务
                    </button>
                  )}
                </section>
                <section>
                  <h2>文件与产物</h2>
                  {!current?.turns.some((t) => t.receipts.some((r) => r.artifact)) && (
                    <p className="cw-muted">本对话还没有生成文件。</p>
                  )}
                  {current?.turns.flatMap((t) =>
                    t.receipts
                      .filter((r) => r.outcome === 'succeeded' && r.artifact)
                      .map((receipt) => {
                        const artifact = receipt.artifact!;
                        const url = `/api/v1/tools/operations/${encodeURIComponent(receipt.operation_id)}/artifact`;
                        return (
                          <div className="cw-file" key={`${t.id}:${receipt.operation_id}`}>
                            <button onClick={() => void openArtifact(artifact.path, url)}>
                              <FileText size={16} />
                              {artifact.path}
                            </button>
                            <a href={url} download aria-label={`下载 ${artifact.path}`}>
                              <Download size={16} />
                            </a>
                          </div>
                        );
                      }),
                  )}
                  {previewLoading && <p role="status">正在读取文件…</p>}
                  {previewError && <p role="alert">{previewError}</p>}
                  {preview && (
                    <div className="cw-preview">
                      <h3>{preview.title}</h3>
                      <Markdown>{preview.text}</Markdown>
                    </div>
                  )}
                </section>
                <section>
                  <h2>最近操作</h2>
                  {run.receipts.length ? (
                    run.receipts.map((receipt) => (
                      <div className="cw-receipt" key={receipt.operation_id}>
                        <Check size={14} />
                        <span>
                          {receipt.tool} ·{' '}
                          {receipt.outcome === 'succeeded'
                            ? '已完成'
                            : receipt.outcome === 'unknown'
                              ? '结果待核对'
                              : '未完成'}
                        </span>
                        <details>
                          <summary>查看结果</summary>
                          <pre>{receipt.output}</pre>
                        </details>
                      </div>
                    ))
                  ) : (
                    <p className="cw-muted">暂无工具操作。</p>
                  )}
                </section>
              </>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
