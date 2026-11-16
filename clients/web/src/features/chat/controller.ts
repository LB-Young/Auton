import type { Session } from '../../shared/contracts';
import type { ApiClient, EventStream } from '../../transport/ports';
import type { ChatController, ChatSnapshot } from './ports';

export function createChatController(api: ApiClient, streams: EventStream): ChatController {
  let state: ChatSnapshot = {
    boot: null,
    sessions: [],
    selected: null,
    loading: true,
    posting: false,
    connected: false,
    error: null,
  };
  const listeners = new Set<() => void>();
  let disconnect: (() => void) | undefined;
  let generation = 0;
  let alive = true;
  let bootGeneration = 0;
  const update = (patch: Partial<ChatSnapshot>) => {
    if (!alive) return;
    state = { ...state, ...patch };
    listeners.forEach((listener) => listener());
  };
  const accept = (session: Session) => {
    const previous = state.sessions.find((item) => item.id === session.id);
    if (previous && previous.sequence > session.sequence) return;
    update({
      sessions: [session, ...state.sessions.filter((item) => item.id !== session.id)],
    });
  };
  const select = (id: string) => {
    disconnect?.();
    const current = ++generation;
    update({ selected: id, connected: false, error: null });
    sessionStorage.setItem('auton.selected', id);
    disconnect = streams.connect(
      id,
      (event) => {
        if (current === generation) accept(event.payload);
      },
      (connected) => {
        if (current === generation) update({ connected });
      },
    );
  };
  const fail = (error: unknown) => {
    update({ error: error instanceof Error ? error.message : '暂时无法连接，请重试' });
  };
  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async start() {
      alive = true;
      const currentBoot = ++bootGeneration;
      disconnect?.();
      generation++;
      update({ loading: true, error: null, selected: null, connected: false });
      try {
        const boot = await api.bootstrap();
        if (!alive || currentBoot !== bootGeneration) return;
        const sessions = boot.demo ? await api.sessions() : [];
        if (!alive || currentBoot !== bootGeneration) return;
        update({ boot, sessions, loading: false });
        const saved = sessionStorage.getItem('auton.selected');
        if (saved && sessions.some((session) => session.id === saved)) select(saved);
        else sessionStorage.removeItem('auton.selected');
      } catch (error) {
        if (!alive || currentBoot !== bootGeneration) return;
        fail(error);
        update({ loading: false });
      }
    },
    dispose() {
      alive = false;
      bootGeneration++;
      generation++;
      disconnect?.();
    },
    select,
    async newSession() {
      if (state.posting || state.loading || !state.boot?.demo) return;
      update({ posting: true, error: null });
      try {
        const session = await api.create(crypto.randomUUID());
        accept(session);
        select(session.id);
      } catch (error) {
        fail(error);
      } finally {
        update({ posting: false });
      }
    },
    async send(content) {
      if (state.posting || !content.trim() || !state.boot?.demo) return false;
      const active = state.sessions.find((session) => session.id === state.selected);
      if (active?.status === 'running' || active?.status === 'stopping') return false;
      update({ posting: true, error: null });
      try {
        let id = state.selected;
        if (!id) {
          const created = await api.create(crypto.randomUUID());
          accept(created);
          select(created.id);
          id = created.id;
        }
        accept(await api.send(id, content, crypto.randomUUID()));
        return true;
      } catch (error) {
        fail(error);
        return false;
      } finally {
        update({ posting: false });
      }
    },
    async stop() {
      const session = state.sessions.find((item) => item.id === state.selected);
      if (!session?.run_id || state.posting) return;
      update({ posting: true, error: null });
      try {
        accept(await api.stop(session.id, session.run_id, crypto.randomUUID()));
      } catch (error) {
        fail(error);
      } finally {
        update({ posting: false });
      }
    },
    clearError: () => update({ error: null }),
  };
}
