import { Operations } from '../features/operations/Operations';
import { Releases } from '../features/release/Releases';
import { Training } from '../features/training/Training';
import { Datasets } from '../features/datasets/Datasets';
import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from 'react';
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Box,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Cpu,
  FileText,
  FlaskConical,
  Folder,
  GraduationCap,
  Layers,
  LoaderCircle,
  MessageSquare,
  Moon,
  PanelLeftClose,
  PanelRight,
  Paperclip,
  Plus,
  Rocket,
  Search,
  Settings,
  Sparkles,
  Square,
  Sun,
  Workflow,
  Wrench,
  X,
} from 'lucide-react';
import type { Application } from './composition';
import type { Artifact, PolicyDecision } from '../shared/contracts';
import { Judgment } from '../features/judgment/Judgment';
import { Tools } from '../features/tools/Tools';
import { Trajectory } from '../features/experience/Trajectory';
import { Agent } from '../features/agent/Agent';
import { DecisionReview } from '../features/decision-review/DecisionReview';
import { Evolution } from '../features/evolution/Evolution';
import { Delegation } from '../features/delegation/Delegation';
import { Assessment } from '../features/assessment/Assessment';
import { Context } from '../features/context/Context';
import { Genome } from '../features/genome/Genome';
import { Models } from '../features/models/Models';
import { Markdown } from '../shared/Markdown';

const workspaces = [
  {
    id: 'operations',
    label: '后台运行',
    icon: Workflow,
    description: '管理资源窗口、队列、监控和恢复。',
  },
  {
    id: 'decision_training',
    label: '决策训练',
    icon: GraduationCap,
    description: '训练决策学生并检查四层证据。',
  },
  {
    id: 'training',
    label: '执行训练',
    icon: GraduationCap,
    description: '配置训练计划、管理作业并复测离线候选。',
  },
  { id: 'context', label: '上下文', icon: BookOpen, description: '查看来源、保留状态与输入预算。' },
  { id: 'tools', label: '工具', icon: Wrench, description: '受控文件、审批与执行凭据。' },
  { id: 'agent', label: '任务', icon: Workflow, description: '查看任务进展、审批与执行记录。' },
  {
    id: 'delegation',
    label: '多 Agent',
    icon: Workflow,
    description: '查看受限委派、依赖和结果集成。',
  },
  {
    id: 'evolve',
    label: '进化',
    icon: FlaskConical,
    description: '诊断技能、评测局部改动并审核候选。',
  },
  {
    id: 'decision_review',
    label: '决策复核',
    icon: FlaskConical,
    description: '查看决策的依据、后续贡献与筛选原因。',
  },
  { id: 'genome', label: '资产', icon: Layers, description: '管理技能、项目知识与长期记忆。' },
  { id: 'model', label: '模型', icon: Cpu, description: '连接执行模型，查看能力与判断来源。' },
  {
    id: 'assess',
    label: '评测',
    icon: FlaskConical,
    description: '用独立证据比较任务与模型表现。',
  },
  {
    id: 'datasets',
    label: '学习',
    icon: GraduationCap,
    description: '从合格历史构建数据和训练候选。',
  },
  { id: 'release', label: '发布', icon: Rocket, description: '审核候选、限定范围灰度并保留回滚。' },
];
const suggestions = [
  {
    icon: Box,
    title: '把想法变成方案',
    text: '帮我设计一个个人知识管理工具',
    category: '规划与设计',
  },
  {
    icon: BookOpen,
    title: '梳理复杂的信息',
    text: '帮我整理一份项目调研计划',
    category: '研究与整理',
  },
  {
    icon: Workflow,
    title: '拆解下一步行动',
    text: '把项目开发拆成可执行的步骤',
    category: '任务与执行',
  },
];

function Brand({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand-mark ${small ? 'small' : ''}`} aria-hidden="true">
      <svg viewBox="0 0 32 32" fill="none">
        <path
          d="M16 4 29 27H3L16 4Z"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        <path
          d="m11 19 5-8 5 8M8.5 23h15"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

export function App({ application }: { application: Application }) {
  const controller = application.chat.controller;
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const session = state.sessions.find((item) => item.id === state.selected);
  const [view, setView] = useState(
    () => new URL(window.location.href).searchParams.get('view') ?? 'agent',
  );
  const agentState = useSyncExternalStore(
    application.agent.controller.subscribe,
    application.agent.controller.getSnapshot,
  );
  const [policyPreview, setPolicyPreview] = useState<PolicyDecision | null>(null);
  const [sidebar, setSidebar] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState<string | null>(null);
  const [panel, setPanel] = useState(false);
  const [panelWidth, setPanelWidth] = useState(400);
  const [theme, setTheme] = useState(() => localStorage.getItem('auton.theme') ?? 'light');
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(null);
  const artifact =
    session?.artifacts.find((item) => item.id === selectedArtifact) ?? session?.artifacts.at(-1);
  const lastArtifact = session?.artifacts.at(-1)?.id;
  const previousArtifact = useRef<string | undefined>(undefined);
  const scrolling = useRef<HTMLDivElement>(null);
  const shouldFollow = useRef(true);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const draftKey = state.selected ?? 'new';
  const draft = drafts[draftKey] ?? '';
  const input = useRef<HTMLTextAreaElement>(null);
  const active = session?.status === 'running' || session?.status === 'stopping';
  const statusText =
    session?.status === 'stopped'
      ? '已停止'
      : session?.status === 'completed'
        ? '演示完成'
        : session?.status === 'stopping'
          ? '正在停止'
          : active
            ? '正在生成'
            : '准备就绪';

  useEffect(() => {
    void controller.start();
    return () => controller.dispose();
  }, [controller]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('auton.theme', theme);
  }, [theme]);

  useEffect(() => {
    if (lastArtifact && lastArtifact !== previousArtifact.current) {
      setPanel(true);
      setSelectedArtifact(lastArtifact);
    }
    previousArtifact.current = lastArtifact;
  }, [lastArtifact]);

  useEffect(() => {
    if (shouldFollow.current && scrolling.current) {
      scrolling.current.scrollTop = scrolling.current.scrollHeight;
    }
  }, [session?.sequence]);

  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSidebar(false);
        setNotice(null);
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'n') {
        event.preventDefault();
        if (view === 'chat') void controller.newSession();
        else {
          application.agent.controller.newRun();
          navigate('agent');
        }
        setSidebar(false);
        setPanel(false);
      }
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [controller, application, view]);

  useEffect(() => {
    if (input.current) {
      input.current.style.height = 'auto';
      input.current.style.height = `${Math.min(input.current.scrollHeight, 180)}px`;
    }
  }, [draft]);

  async function send() {
    const content = draft.trim();
    if (!content || active) return;
    shouldFollow.current = true;
    const key = draftKey;
    if (await controller.send(content)) {
      setDrafts((old) => (old[key]?.trim() === content ? { ...old, [key]: '' } : old));
    } else {
      const destination = controller.getSnapshot().selected ?? key;
      setDrafts((old) => ({ ...old, [destination]: content }));
    }
  }

  useEffect(() => {
    const restore = () =>
      setView(new URL(window.location.href).searchParams.get('view') ?? 'agent');
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);

  function navigate(id: string) {
    setView(id);
    const url = new URL(window.location.href);
    url.searchParams.set('view', id);
    window.history.replaceState(null, '', url);
    setSidebar(false);
  }

  async function newChat() {
    if (view !== 'chat') {
      application.agent.controller.newRun();
      navigate('agent');
      return;
    }
    setView('chat');
    setSidebar(false);
    setPanel(false);
    await controller.newSession();
    input.current?.focus();
  }

  function download(item: Artifact) {
    const url = URL.createObjectURL(
      new Blob([item.content], { type: 'text/markdown;charset=utf-8' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = item.filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  const selectedWorkspace = workspaces.find((item) => item.id === view);
  const module = state.boot?.modules.find((item) => item.id === view);

  return (
    <div
      className={`app ${collapsed ? 'sidebar-collapsed' : ''}`}
      style={{ '--artifact-width': `${panelWidth}px` } as CSSProperties}
    >
      {sidebar && (
        <button
          className="sidebar-overlay"
          aria-label="关闭导航遮罩"
          onClick={() => setSidebar(false)}
        />
      )}
      <aside className={`sidebar ${sidebar ? 'mobile-open' : ''}`} aria-label="主导航">
        <div className="brand-row">
          <a
            className="brand"
            href="#"
            onClick={(event) => {
              event.preventDefault();
              navigate('agent');
            }}
          >
            <Brand />
            <span>
              Auton<span className="brand-period">.</span>
            </span>
          </a>
          <button
            className="icon-button collapse-button"
            title="折叠导航"
            aria-label="折叠导航"
            onClick={() => {
              setCollapsed(true);
              setSidebar(false);
            }}
          >
            <PanelLeftClose size={18} />
          </button>
        </div>
        <button
          className="new-chat"
          onClick={() => void newChat()}
          disabled={
            state.loading ||
            state.posting ||
            agentState.busy ||
            (view === 'chat' && !state.boot?.demo)
          }
        >
          <Plus size={17} />
          {view === 'chat' ? '新对话' : '新任务'}
          <span>⌘ N</span>
        </button>
        <button
          className="nav-item search-button"
          onClick={() => setSearch(search === null ? '' : null)}
        >
          <Search size={17} />
          {view === 'chat' ? '搜索对话' : '搜索任务'}
        </button>
        {search !== null && (
          <input
            className="history-search"
            autoFocus
            aria-label={view === 'chat' ? '搜索历史对话' : '导航搜索任务'}
            placeholder="输入对话标题…"
            value={view === 'chat' ? search : agentState.search}
            onChange={(event) => {
              if (view === 'chat') setSearch(event.target.value);
              else void application.agent.controller.search(event.target.value);
            }}
          />
        )}
        <button className="nav-item" onClick={() => navigate(view === 'chat' ? 'agent' : 'chat')}>
          {view === 'chat' ? '返回真实任务' : '演示对话 · Demo'}
        </button>
        {view === 'agent' && (
          <div className="real-history-nav">
            <p className="nav-section-label">当前项目</p>
            <select
              aria-label="导航项目"
              value={agentState.project}
              disabled={agentState.busy}
              onChange={(event) => void application.agent.controller.project(event.target.value)}
            >
              {agentState.projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.title}
                </option>
              ))}
            </select>
            {agentState.runs
              .slice(-12)
              .reverse()
              .map((run) => (
                <button
                  className="history-item"
                  disabled={agentState.busy}
                  key={run.id}
                  aria-label={`打开任务 ${run.command.goal.slice(0, 32)}`}
                  onClick={() => {
                    void application.agent.controller.select(run.id);
                    setSidebar(false);
                  }}
                >
                  <MessageSquare size={14} />
                  <span>{run.command.goal.slice(0, 32)}</span>
                </button>
              ))}
          </div>
        )}
        {view === 'chat' && (
          <>
            <div className="nav-section-label">演示会话</div>
            <button
              className={`nav-item ${view === 'chat' ? 'selected' : ''}`}
              onClick={() => navigate('chat')}
            >
              <Folder size={17} />
              个人工作区
              <ChevronDown size={14} className="nav-end" />
            </button>
            <div className="history-list">
              {state.sessions
                .filter((item) => search === null || item.title.includes(search))
                .slice(0, 12)
                .map((item) => (
                  <button
                    key={item.id}
                    className={`history-item ${state.selected === item.id && view === 'chat' ? 'current' : ''}`}
                    onClick={() => {
                      controller.select(item.id);
                      shouldFollow.current = true;
                      setPanel(false);
                      navigate('chat');
                    }}
                  >
                    <MessageSquare size={14} />
                    <span>{item.title}</span>
                    {item.status === 'running' && <span className="running-dot" />}
                  </button>
                ))}
              {!state.sessions.length && (
                <p className="history-empty">
                  想法、进展和对话
                  <br />
                  将在这里串联起来。
                </p>
              )}
              {search && !state.sessions.some((item) => item.title.includes(search)) && (
                <p className="history-empty">没有匹配的对话</p>
              )}
            </div>
          </>
        )}
        <div className="nav-section-label workspace-label">
          工作区 <span>模块</span>
        </div>
        <nav className="workspace-nav">
          {workspaces.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${view === item.id ? 'selected' : ''}`}
              onClick={() => navigate(item.id)}
            >
              <item.icon size={17} />
              {item.label}
              <span className="planned-label">
                {state.boot?.modules.some(
                  (module) => module.id === item.id && module.status === 'ready',
                )
                  ? '已接入'
                  : '待开发'}
              </span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="foundation-card">
            <span className="foundation-icon">
              <Layers size={15} />
            </span>
            <div>
              <strong>从基础，逐步生长</strong>
              <p>项目框架 · 第一个里程碑</p>
            </div>
          </div>
          <button
            className={`nav-item ${view === 'settings' ? 'selected' : ''}`}
            onClick={() => navigate('settings')}
          >
            <Settings size={17} />
            设置与连接
            <ChevronRight size={14} className="nav-end" />
          </button>
          <div className="profile-row">
            <span className="avatar">Y</span>
            <div>
              <strong>个人空间</strong>
              <span>本地工作台</span>
            </div>
            <span
              className={`connection-dot ${state.boot ? 'online' : ''}`}
              title={state.boot ? '服务已连接' : '服务未连接'}
            />
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <button
            className="icon-button open-sidebar"
            aria-label="展开导航"
            onClick={() => {
              setCollapsed(false);
              setSidebar(true);
            }}
          >
            <PanelLeftClose size={19} />
          </button>
          <div className="breadcrumb">
            <span>个人工作区</span>
            <ChevronRight size={13} />
            <strong>
              {view === 'chat'
                ? (session?.title ?? '新对话')
                : (selectedWorkspace?.label ?? '设置与连接')}
            </strong>
          </div>
          <div className="topbar-actions">
            <span className="demo-badge">
              <span />
              {view === 'agent'
                ? '任务工作台'
                : state.boot?.demo === false
                  ? '真实任务已接入'
                  : '框架演示'}
            </span>
            <span className="topbar-divider" />
            <button
              className="icon-button"
              aria-label={theme === 'light' ? '切换深色主题' : '切换浅色主题'}
              onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
            >
              {theme === 'light' ? <Moon size={17} /> : <Sun size={17} />}
            </button>
            {view === 'chat' && (
              <button
                className={`icon-button ${panel ? 'pressed' : ''}`}
                aria-label="切换产物面板"
                aria-expanded={panel}
                onClick={() => setPanel(!panel)}
              >
                <PanelRight size={18} />
              </button>
            )}
          </div>
        </header>
        <div className="workspace-body">
          <main className={`main ${view !== 'chat' ? 'module-main' : ''}`}>
            {view === 'chat' ? (
              <>
                <div
                  className="conversation-scroll"
                  ref={scrolling}
                  onScroll={() => {
                    const node = scrolling.current;
                    if (node)
                      shouldFollow.current =
                        node.scrollHeight - node.scrollTop - node.clientHeight < 100;
                  }}
                >
                  {!session?.messages.length ? (
                    <section className="welcome">
                      <div className="welcome-icon">
                        <Brand />
                        <span className="welcome-orbit" />
                      </div>
                      <p className="eyebrow">留一点空间，给新的可能</p>
                      <h1>今天，想一起完成什么？</h1>
                      <p className="welcome-description">
                        从一个想法到一份成果，让每一步都有方向。
                      </p>
                      <div className="suggestions">
                        {suggestions.map((item) => (
                          <button
                            key={item.title}
                            onClick={() => {
                              setDrafts((old) => ({ ...old, [draftKey]: item.text }));
                              input.current?.focus();
                            }}
                          >
                            <span className="suggestion-icon">
                              <item.icon size={20} strokeWidth={1.6} />
                            </span>
                            <strong>
                              {item.title}
                              <ArrowUpRight size={14} />
                            </strong>
                            <span className="suggestion-category">{item.category}</span>
                          </button>
                        ))}
                      </div>
                      <div className="welcome-footnote">
                        <span className="little-dot" />
                        你的个人 Agent，正在从这里搭建
                      </div>
                    </section>
                  ) : (
                    <div className="messages">
                      <div className="conversation-label">
                        今天 <span>仅在当前服务内存中保留</span>
                      </div>
                      {session.messages.map((message) => (
                        <article key={message.id} className={`message ${message.role}`}>
                          {message.role === 'assistant' && (
                            <div className="assistant-label">
                              <Brand small />
                              <strong>Auton</strong>
                              <span>DEMO</span>
                            </div>
                          )}
                          {message.content ? (
                            <Markdown>{message.content}</Markdown>
                          ) : (
                            <div className="typing-indicator" aria-label="正在准备演示回复">
                              <i />
                              <i />
                              <i />
                            </div>
                          )}
                          {message.role === 'assistant' &&
                            message.id === session.messages.at(-1)?.id &&
                            !active && (
                              <div className="message-footnote">
                                <Check size={13} />
                                {statusText} · 模拟输出
                              </div>
                            )}
                        </article>
                      ))}
                      {session.artifacts.length > 0 && (
                        <div className="artifact-cards">
                          {session.artifacts.map((item) => (
                            <button
                              key={item.id}
                              onClick={() => {
                                setSelectedArtifact(item.id);
                                setPanel(true);
                              }}
                            >
                              <span className="file-icon">
                                <FileText size={22} />
                              </span>
                              <span>
                                <strong>{item.title}</strong>
                                <small>Markdown · 合成示例</small>
                              </span>
                              <ArrowUpRight size={17} />
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <div className="composer-area">
                  {state.error && (
                    <div className="error-banner" role="alert">
                      <span>{state.error}</span>
                      <button
                        onClick={() =>
                          state.boot ? controller.clearError() : void controller.start()
                        }
                      >
                        {state.boot ? '关闭' : '重试连接'}
                      </button>
                    </div>
                  )}
                  {notice && (
                    <div className="notice-banner" role="status">
                      {notice}
                      <button
                        className="icon-button"
                        aria-label="关闭提示"
                        onClick={() => setNotice(null)}
                      >
                        <X size={14} />
                      </button>
                    </div>
                  )}
                  {state.boot && !state.boot.demo && (
                    <div className="notice-banner">
                      真实 Agent 将在后续里程碑接入；当前配置未启用演示。
                    </div>
                  )}
                  {session && !state.connected && (
                    <div className="reconnect-banner" role="status">
                      事件流正在重新连接，服务端任务不受影响。
                      <button onClick={() => void controller.start()}>刷新连接</button>
                    </div>
                  )}
                  <div className={`composer ${active ? 'is-active' : ''}`}>
                    <textarea
                      ref={input}
                      aria-label="任务输入"
                      placeholder={
                        state.loading ? '正在连接你的工作空间…' : '描述你的想法，或交给我一个任务…'
                      }
                      rows={2}
                      maxLength={8000}
                      value={draft}
                      disabled={!state.boot?.demo || state.loading || state.posting}
                      onChange={(event) =>
                        setDrafts((old) => ({ ...old, [draftKey]: event.target.value }))
                      }
                      onKeyDown={(event) => {
                        if (
                          event.key === 'Enter' &&
                          !event.shiftKey &&
                          !event.nativeEvent.isComposing &&
                          event.keyCode !== 229
                        ) {
                          event.preventDefault();
                          void send();
                        }
                      }}
                    />
                    <div className="composer-toolbar">
                      <div className="composer-options">
                        <button
                          className="icon-button"
                          aria-label="附件将在工具模块接入"
                          title="附件将在 M06/M12 接入"
                          onClick={() => setNotice('附件上传将在后续工具模块中接入。')}
                        >
                          <Paperclip size={18} />
                        </button>
                        <span className="composer-divider" />
                        <span className="model-pill">
                          <Sparkles size={13} />
                          {state.boot?.demo
                            ? `Demo · ${state.boot.implementation === 'echo' ? 'Echo' : 'Scripted'}`
                            : '未连接模型'}
                        </span>
                      </div>
                      <div className="send-options">
                        <span className="keyboard-hint">{active ? statusText : '↵ 发送'}</span>
                        {active ? (
                          <button
                            className="send-button stop-button"
                            aria-label="停止生成"
                            disabled={state.posting || session?.status === 'stopping'}
                            onClick={() => void controller.stop()}
                          >
                            {state.posting ? (
                              <LoaderCircle size={17} className="spin" />
                            ) : (
                              <Square size={14} fill="currentColor" />
                            )}
                          </button>
                        ) : (
                          <button
                            className="send-button"
                            aria-label="发送消息"
                            disabled={!draft.trim() || state.posting || !state.boot?.demo}
                            onClick={() => void send()}
                          >
                            {state.posting ? (
                              <LoaderCircle size={19} className="spin" />
                            ) : (
                              <ArrowUp size={20} />
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="composer-caption">
                    <span>框架演示 · 不调用真实模型，不执行工具</span>
                    <span className="caption-help">
                      <CircleHelp size={12} />
                      M01
                    </span>
                  </div>
                </div>
              </>
            ) : view === 'agent' && !state.boot ? (
              <section className="module-page">
                <p role="status">{state.error ?? '正在连接你的工作空间…'}</p>
                <button className="secondary-button" onClick={() => void controller.start()}>
                  重试连接
                </button>
              </section>
            ) : view === 'agent' ? (
              <Agent
                feature={application.agent}
                onNavigate={navigate}
                renderArtifact={application.artifacts.renderText}
                renderTrajectory={(run, onRecovered) => (
                  <Trajectory
                    feature={application.experience}
                    run={run}
                    onRecovered={onRecovered}
                  />
                )}
              />
            ) : view === 'context' ? (
              <Context feature={application.context} />
            ) : view === 'genome' ? (
              <Genome feature={application.genome} />
            ) : view === 'tools' ? (
              <Tools feature={application.tools} />
            ) : view === 'model' ? (
              <div className="model-workspace">
                <Models feature={application.models} />
                <div className="judgment-workspace">
                  <Judgment feature={application.judgment} />
                </div>
              </div>
            ) : view === 'delegation' ? (
              <Delegation feature={application.delegation} />
            ) : view === 'decision_review' ? (
              <DecisionReview feature={application.decisionReview} />
            ) : view === 'decision_training' ? (
              <Training feature={application.decisionTraining} />
            ) : view === 'training' ? (
              <Training feature={application.training} />
            ) : view === 'operations' ? (
              <Operations feature={application.operations} />
            ) : view === 'release' ? (
              <Releases feature={application.releases} />
            ) : view === 'datasets' ? (
              <Datasets feature={application.datasets} />
            ) : view === 'evolve' ? (
              <Evolution feature={application.evolution} />
            ) : view === 'assess' ? (
              <Assessment feature={application.assessment} />
            ) : view === 'settings' ? (
              <section className="module-page">
                <p className="eyebrow">你的工作空间</p>
                <h1>设置与连接</h1>
                <p className="module-description">查看当前能力，保持每一步真实可见。</p>
                <div className="settings-card">
                  <h2>连接状态</h2>
                  <button
                    className="secondary-button"
                    onClick={() => {
                      const project = window.prompt(
                        '输入旧身份拥有的项目 ID，以恢复升级前的本机身份。需要此浏览器仍保留旧 Cookie。',
                      );
                      if (project)
                        void application
                          .adoptLegacy(project)
                          .then(() => window.location.reload())
                          .catch((error: Error) => setNotice(error.message));
                    }}
                  >
                    恢复升级前的本机身份
                  </button>
                  <p>
                    本机身份：{state.boot?.identity?.identity_id ?? '不可用'} ·{' '}
                    {state.boot?.identity?.persistent ? '重启后保持' : '测试临时身份'}
                  </p>
                  <button
                    className="secondary-button"
                    onClick={() => {
                      if (window.confirm('创建新本机身份后，旧身份的数据不会转移。确认继续？'))
                        void application
                          .resetIdentity()
                          .then(() => window.location.reload())
                          .catch((error: Error) => setNotice(error.message));
                    }}
                  >
                    创建新的本机身份
                  </button>
                  <dl>
                    <div>
                      <dt>后端服务</dt>
                      <dd>
                        <span className={`connection-dot ${state.boot ? 'online' : ''}`} />
                        {state.boot ? '已连接' : '未连接'}
                      </dd>
                    </div>
                    <div>
                      <dt>运行配置</dt>
                      <dd>{state.boot?.profile ?? '不可用'}</dd>
                    </div>
                    <div>
                      <dt>事件日志</dt>
                      <dd>
                        {state.boot?.event_storage?.ready
                          ? `${state.boot.event_storage.backend === 'sqlite' ? 'SQLite' : '测试内存'} · ${state.boot.event_storage.journal_mode}/${state.boot.event_storage.synchronous}`
                          : '未就绪'}
                      </dd>
                    </div>
                    <div>
                      <dt>会话存储</dt>
                      <dd>仅内存 · 重启服务后清空</dd>
                    </div>
                    <div>
                      <dt>判断与模型</dt>
                      <dd>执行模型与本地 Laya 判断已接入；模型页可分别检测</dd>
                    </div>
                  </dl>
                </div>
                <div className="settings-card">
                  <h2>权限与预算</h2>
                  <dl>
                    <div>
                      <dt>策略版本</dt>
                      <dd>{state.boot?.policy?.version ?? '服务尚未提供'}</dd>
                    </div>
                    <div>
                      <dt>允许外发至</dt>
                      <dd>
                        {state.boot?.policy?.remote_providers.length
                          ? state.boot.policy.remote_providers.join('、')
                          : '未授权外发'}
                      </dd>
                    </div>
                    <div>
                      <dt>外发数据范围</dt>
                      <dd>仅明确标记为公开的数据；私密与密钥留在本地</dd>
                    </div>
                    <div>
                      <dt>单目标 token 上限</dt>
                      <dd>
                        {state.boot?.policy?.budget_per_goal.tokens.toLocaleString() ?? '未就绪'}
                      </dd>
                    </div>
                    <div>
                      <dt>单目标费用上限</dt>
                      <dd>
                        {state.boot?.policy
                          ? `$${(state.boot.policy.budget_per_goal.cost_microusd / 1000000).toFixed(2)}`
                          : '未就绪'}
                      </dd>
                    </div>
                    <div>
                      <dt>需批准的动作</dt>
                      <dd>{state.boot?.policy?.approval_actions.join('、') ?? '未就绪'}</dd>
                    </div>
                  </dl>
                  <div className="composer-options">
                    <button
                      className="secondary-button"
                      onClick={() =>
                        void application.policy
                          .preview('private-remote')
                          .then(setPolicyPreview)
                          .catch(() => setNotice('预检服务暂不可用'))
                      }
                    >
                      检查私密数据外发
                    </button>
                    <button
                      className="secondary-button"
                      onClick={() =>
                        void application.policy
                          .preview('tool-write')
                          .then(setPolicyPreview)
                          .catch(() => setNotice('预检服务暂不可用'))
                      }
                    >
                      检查工具写入
                    </button>
                  </div>
                  {policyPreview && (
                    <p className="notice-banner" role="status">
                      {policyPreview.outcome === 'deny'
                        ? '禁止执行'
                        : policyPreview.outcome === 'approval_required'
                          ? '需要批准'
                          : '预检允许'}{' '}
                      · 仅预检，未执行任何动作
                    </p>
                  )}
                  <p className="module-note">
                    预检通过不代表已执行。真实动作审批在工具/发布模块接入；已派发操作需对账后才能释放预算。
                  </p>
                </div>
                <div className="settings-card">
                  <h2>外观</h2>
                  <button
                    className="secondary-button"
                    onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
                  >
                    {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}切换到
                    {theme === 'light' ? '深色' : '浅色'}主题
                  </button>
                </div>
                <p className="module-note">
                  本机工作台已接入持久事件、固定策略与执行模型网关。真实 Agent
                  已接入任务页；主对话仍为 Demo。
                </p>
              </section>
            ) : (
              <section className="module-page planned-page">
                <span className="module-icon">
                  {selectedWorkspace && <selectedWorkspace.icon size={30} strokeWidth={1.4} />}
                </span>
                <p className="eyebrow">逐步搭建，保持清晰</p>
                <h1>{selectedWorkspace?.label ?? '工作区'}</h1>
                <p className="module-description">{selectedWorkspace?.description}</p>
                <span className="milestone-badge">
                  {module?.milestone ?? '后续里程碑'} · 待开发
                </span>
                <p className="module-note">
                  这里还没有真实数据或操作。
                  <br />
                  当前可以在对话中体验框架的完整演示链路。
                </p>
                <button className="secondary-button" onClick={() => navigate('chat')}>
                  返回对话
                  <ArrowRight size={15} />
                </button>
              </section>
            )}
          </main>
          {panel && view === 'chat' && (
            <>
              <div
                className="resize-handle"
                role="separator"
                aria-label="调整产物面板宽度"
                aria-orientation="vertical"
                aria-valuenow={panelWidth}
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                    event.preventDefault();
                    setPanelWidth((value) =>
                      Math.min(600, Math.max(320, value + (event.key === 'ArrowLeft' ? 20 : -20))),
                    );
                  }
                }}
                onPointerDown={(event) => event.currentTarget.setPointerCapture(event.pointerId)}
                onPointerMove={(event) => {
                  if (event.buttons === 1)
                    setPanelWidth(Math.min(600, Math.max(320, window.innerWidth - event.clientX)));
                }}
              />
              <aside className="artifact-panel" aria-label="产物面板">
                <header>
                  <div>
                    <FileText size={17} />
                    <strong>工作产物</strong>
                    {session?.artifacts.length ? (
                      <span className="count-badge">{session.artifacts.length}</span>
                    ) : null}
                  </div>
                  <button
                    className="icon-button"
                    aria-label="关闭产物面板"
                    onClick={() => setPanel(false)}
                  >
                    <X size={18} />
                  </button>
                </header>
                {artifact ? (
                  <>
                    <div className="artifact-meta">
                      <span className="artifact-type">MARKDOWN</span>
                      <h2>{artifact.title}</h2>
                      <div>
                        <span>{artifact.filename}</span>
                        <button
                          className="icon-button"
                          aria-label="下载合成笔记"
                          title="下载合成笔记"
                          onClick={() => download(artifact)}
                        >
                          <ArrowDownToLine size={15} />
                        </button>
                      </div>
                    </div>
                    <div className="artifact-content">{application.artifacts.render(artifact)}</div>
                    <footer>
                      <span className="little-dot" />
                      合成产物 · 未写入项目文件
                    </footer>
                  </>
                ) : (
                  <div className="artifact-empty">
                    <FileText size={32} strokeWidth={1} />
                    <h2>让成果有处安放</h2>
                    <p>
                      演示完成后，合成笔记会出现在这里。
                      <br />
                      你也可以随时收起这个面板。
                    </p>
                  </div>
                )}
              </aside>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
