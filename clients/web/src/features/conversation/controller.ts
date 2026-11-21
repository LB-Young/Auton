import type {
  AgentRun,
  ConversationTurn,
  ConversationView,
  ModelInfo,
  RunCommand,
  RunSnapshot,
  WorkspaceConversation,
} from '../../shared/contracts';
import type { ApiClient } from '../../transport/ports';

export interface ConversationState {
  conversations: WorkspaceConversation[];
  current: ConversationView | null;
  models: ModelInfo[];
  model: string;
  draft: string;
  loading: boolean;
  busy: boolean;
  error: string;
  progress: RunSnapshot['transient'];
}
export const finished = (run: AgentRun) =>
  ['succeeded', 'failed', 'cancelled'].includes(run.status);

export function createConversationController(api: ApiClient) {
  let state: ConversationState = {
    conversations: [],
    current: null,
    models: [],
    model: '',
    draft: '',
    loading: true,
    busy: false,
    error: '',
    progress: null,
  };
  const listeners = new Set<() => void>();
  const drafts = new Map<string, string>();
  const pending = new Map<string, ConversationTurn>();
  const controls = new Map<string, RunCommand>();
  let alive = false,
    generation = 0,
    selection = 0;
  let createRequest = crypto.randomUUID();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const update = (patch: Partial<ConversationState>) => {
    state = { ...state, ...patch };
    listeners.forEach((fn) => fn());
  };
  const fail = (error: unknown) =>
    update({ error: error instanceof Error ? error.message : '连接失败，请重试' });
  const route = () => {
    const url = new URL(window.location.href);
    url.searchParams.set('view', 'workspace');
    url.searchParams.delete('project');
    url.searchParams.delete('run');
    url.searchParams.delete('legacy');
    if (state.current) url.searchParams.set('conversation', state.current.conversation.id);
    else url.searchParams.delete('conversation');
    window.history.replaceState(null, '', url);
  };
  const accept = (run: AgentRun) => {
    if (!state.current?.turns.some((r) => r.id === run.id)) return;
    update({
      current: {
        ...state.current,
        turns: state.current.turns.map((r) =>
          r.id === run.id && r.version <= run.version ? run : r,
        ),
      },
    });
  };
  const watch = () => {
    clearTimeout(timer);
    const run = state.current?.turns.at(-1),
      selected = selection,
      epoch = generation;
    if (!run || finished(run)) return;
    const poll = async () => {
      if (!alive || epoch !== generation || selected !== selection) return;
      try {
        const snapshot = await api.runSnapshot(run.id);
        if (!alive || epoch !== generation || selected !== selection) return;
        accept(snapshot.run);
        update({ progress: snapshot.transient, error: '' });
        if (finished(snapshot.run)) return;
      } catch (error) {
        if (!alive || epoch !== generation || selected !== selection) return;
        fail(error);
      }
      if (alive && epoch === generation && selected === selection)
        timer = setTimeout(() => void poll(), 800);
    };
    void poll();
  };
  const controller = {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    getSnapshot: () => state,
    async start() {
      alive = true;
      const epoch = ++generation;
      update({ loading: true, error: '' });
      try {
        await api.bootstrap();
        const [models, conversations] = await Promise.all([api.models(), api.conversations.list()]);
        if (!alive || epoch !== generation) return;
        update({
          models,
          conversations,
          model:
            state.model ||
            models.find((m) => m.health !== 'unavailable' && m.health !== 'credential_missing')
              ?.id ||
            models[0]?.id ||
            '',
          loading: false,
        });
        const id = new URL(window.location.href).searchParams.get('conversation');
        if (id) await controller.select(id);
      } catch (error) {
        if (alive && epoch === generation) {
          fail(error);
          update({ loading: false });
        }
      }
    },
    dispose() {
      alive = false;
      generation++;
      selection++;
      clearTimeout(timer);
    },
    draft(text: string) {
      drafts.set(state.current?.conversation.id ?? 'new', text);
      update({ draft: text });
    },
    model(id: string) {
      if (state.models.some((m) => m.id === id)) update({ model: id });
    },
    newConversation() {
      if (state.busy) return;
      selection++;
      clearTimeout(timer);
      createRequest = crypto.randomUUID();
      drafts.delete('new');
      pending.clear();
      controls.clear();
      update({ current: null, draft: '', progress: null, error: '', loading: false });
      route();
    },
    async select(id: string) {
      if (state.busy) return;
      const selected = ++selection;
      clearTimeout(timer);
      update({ loading: true, progress: null, error: '' });
      try {
        const current = await api.conversations.view(id);
        if (!alive || selected !== selection) return;
        // A reload after an uncertain send should reconcile that draft with its durable turn.
        for (const [key, command] of pending) {
          const [conversationId] = JSON.parse(key) as [string];
          const recovered = current.turns[command.expected_turns];
          if (
            conversationId === id &&
            recovered?.command.goal === command.text &&
            recovered.command.model_id === command.model_id
          ) {
            pending.delete(key);
            if (drafts.get(id)?.trim() === command.text) drafts.delete(id);
          }
        }
        update({ current, draft: drafts.get(id) ?? '', loading: false });
        route();
        watch();
      } catch (error) {
        if (alive && selected === selection) {
          fail(error);
          update({ loading: false });
        }
      }
    },
    async send() {
      if (state.busy || state.loading || !state.draft.trim() || !state.model) return false;
      if ((state.current?.turns.length ?? 0) >= 40) {
        update({ error: '本对话已达 40 轮，请新建对话继续。' });
        return false;
      }
      const last = state.current?.turns.at(-1);
      if (last && !finished(last)) {
        update({ error: '当前任务尚未结束，请先在工作面板处理或停止。' });
        return false;
      }
      const text = state.draft.trim(),
        model = state.models.find((m) => m.id === state.model);
      if (!model) return false;
      update({ busy: true, error: '' });
      try {
        let current = state.current;
        if (!current) {
          const conversation = await api.conversations.create({
            request_id: createRequest,
            title: text.slice(0, 80),
          });
          current = { conversation, turns: [] };
          update({
            current,
            conversations: [
              conversation,
              ...state.conversations.filter((c) => c.id !== conversation.id),
            ],
          });
          route();
          drafts.set(conversation.id, text);
        }
        const key = JSON.stringify([current.conversation.id, current.turns.length, text, model.id]);
        if (!pending.has(key))
          pending.set(key, {
            request_id: crypto.randomUUID(),
            expected_turns: current.turns.length,
            text,
            model_id: model.id,
            allow_remote: model.location === 'remote',
          });
        const run = await api.conversations.send(current.conversation.id, pending.get(key)!);
        pending.delete(key);
        drafts.delete(current.conversation.id);
        drafts.delete('new');
        update({ current: { ...current, turns: [...current.turns, run] }, draft: '', busy: false });
        watch();
        return true;
      } catch (error) {
        fail(error);
        update({ busy: false });
        return false;
      }
    },
    async command(action: RunCommand['action']) {
      const run = state.current?.turns.at(-1);
      if (!run || state.busy) return;
      const key = `${run.id}:${run.version}:${action}`;
      if (!controls.has(key))
        controls.set(key, {
          request_id: crypto.randomUUID(),
          expected_goal_revision: run.goal_revision,
          expected_version: run.version,
          action,
        });
      update({ busy: true, error: '' });
      try {
        const result = await api.agentCommand(run.id, controls.get(key)!);
        accept(result);
        controls.delete(key);
        watch();
      } catch (error) {
        fail(error);
      } finally {
        update({ busy: false });
      }
    },
  };
  return controller;
}
