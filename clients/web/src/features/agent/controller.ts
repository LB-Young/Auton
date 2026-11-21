import type { AgentRun, RunCommand } from '../../shared/contracts';
import type { ApiClient, RunEventStream } from '../../transport/ports';
import type { ProjectsPort } from '../projects/ports';
import type { AgentController, AgentSnapshot } from './ports';

export function createAgentController(
  api: ApiClient,
  events: RunEventStream,
  send: (id: string, command: RunCommand) => Promise<AgentRun>,
  projectsPort: ProjectsPort,
  onNew: () => void,
): AgentController {
  let state: AgentSnapshot = {
    draftVersion: 0,
    projects: [],
    workspaces: [],
    models: [],
    project: '',
    runs: [],
    run: null,
    next: null,
    search: '',
    loading: true,
    busy: false,
    connected: false,
    error: '',
    progress: null,
  };
  const listeners = new Set<() => void>();
  let alive = false,
    epoch = 0,
    selection = 0,
    query = 0;
  let disconnect: (() => void) | undefined;
  const update = (patch: Partial<AgentSnapshot>) => {
    state = { ...state, ...patch };
    listeners.forEach((fn) => fn());
  };
  const fail = (error: unknown) =>
    update({ error: error instanceof Error ? error.message : '任务连接失败' });
  const route = () => {
    const url = new URL(window.location.href);
    if (state.project) url.searchParams.set('project', state.project);
    else url.searchParams.delete('project');
    if (state.run) url.searchParams.set('run', state.run.id);
    else url.searchParams.delete('run');
    window.history.replaceState(null, '', url);
  };
  const accept = (run: AgentRun) => {
    if (run.command.project_id !== state.project) return;
    const previous = state.runs.find((r) => r.id === run.id);
    if (previous && previous.version > run.version) return;
    const matches = run.command.goal.toLocaleLowerCase().includes(state.search.toLocaleLowerCase());
    update({
      runs: !matches
        ? state.runs.filter((r) => r.id !== run.id)
        : previous
          ? state.runs.map((r) => (r.id === run.id ? run : r))
          : [...state.runs, run],
      run: !state.run || state.run.id === run.id ? run : state.run,
    });
  };
  async function loadPage(append: boolean) {
    const current = ++query,
      generation = epoch,
      project = state.project;
    if (!project) return;
    update({ loading: true, error: '' });
    try {
      const page = await api.runHistory(project, append ? (state.next ?? 0) : 0, state.search);
      if (!alive || generation !== epoch || current !== query) return;
      const values = append ? [...state.runs] : [];
      for (const run of page.items) {
        const i = values.findIndex((r) => r.id === run.id);
        if (i < 0) values.push(run);
        else if (values[i].version <= run.version) values[i] = run;
      }
      update({ runs: values, next: page.next_cursor, loading: false });
    } catch (error) {
      if (alive && generation === epoch && current === query) {
        fail(error);
        update({ loading: false });
      }
    }
  }
  const attach = (id: string) => {
    disconnect?.();
    const current = ++selection;
    let fetching = false,
      again = false;
    update({ connected: false, progress: null });
    const valid = () => alive && current === selection;
    const refresh = async () => {
      if (fetching) {
        again = true;
        return;
      }
      fetching = true;
      try {
        const snapshot = await api.runSnapshot(id);
        if (!valid()) return;
        accept(snapshot.run);
        if (state.run?.id !== id || state.run.version > snapshot.run.version) return;
        const old = state.progress,
          next = snapshot.transient;
        update({
          progress:
            old &&
            old.request_id === snapshot.run.model_request_id &&
            old.version === snapshot.run.version &&
            (!next || old.sequence > next.sequence)
              ? old
              : next,
        });
      } catch (error) {
        if (valid()) fail(error);
      } finally {
        fetching = false;
        if (valid() && again) {
          again = false;
          void refresh();
        }
      }
    };
    void refresh();
    disconnect = events.connect(
      id,
      (frame) => {
        if (!valid()) return;
        if (frame.kind === 'delta' && frame.progress) {
          const next = frame.progress,
            old = state.progress;
          if (!old || old.request_id !== next.request_id || old.sequence <= next.sequence)
            update({ progress: next });
        } else if (frame.kind !== 'heartbeat') void refresh();
      },
      (connected) => {
        if (valid()) {
          update({ connected });
          if (connected) void refresh();
        }
      },
    );
  };
  const controller: AgentController = {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    async start() {
      alive = true;
      selection++;
      disconnect?.();
      const current = ++epoch;
      update({ loading: true, error: '', run: null, progress: null, connected: false });
      try {
        const [projects, workspaces, models] = await Promise.all([
          projectsPort.list(),
          api.toolWorkspaces(),
          api.models(),
        ]);
        if (!alive || current !== epoch) return;
        const url = new URL(window.location.href);
        const requested = url.searchParams.get('project');
        const project =
          requested ??
          (projects.some((p) => p.id === state.project) ? state.project : (projects[0]?.id ?? ''));
        update({ projects, workspaces, models });
        if (requested && !projects.some((p) => p.id === requested))
          throw new Error('链接中的项目不可访问，请选择你拥有的项目');
        update({ projects, workspaces, models, project, loading: false, run: null, runs: [] });
        if (project) await loadPage(false);
        if (!alive || current !== epoch) return;
        const run = url.searchParams.get('run');
        if (run) await controller.select(run);
      } catch (error) {
        if (alive && current === epoch) {
          fail(error);
          update({ loading: false });
        }
      }
    },
    dispose() {
      alive = false;
      epoch++;
      selection++;
      query++;
      disconnect?.();
    },
    async project(project) {
      epoch++;
      selection++;
      query++;
      disconnect?.();
      update({
        project,
        run: null,
        runs: [],
        next: null,
        search: '',
        progress: null,
        connected: false,
      });
      route();
      await loadPage(false);
    },
    async search(search) {
      update({ search });
      await loadPage(false);
    },
    more: () => loadPage(true),
    async select(id) {
      const current = ++selection,
        generation = epoch;
      disconnect?.();
      update({ error: '', run: null, connected: false, progress: null });
      try {
        const run = await api.agentRun(id);
        if (!alive || generation !== epoch || current !== selection) return;
        if (run.command.project_id !== state.project) throw new Error('任务与当前项目不匹配');
        update({ run });
        accept(run);
        route();
        attach(id);
      } catch (error) {
        if (alive && generation === epoch && current === selection) fail(error);
      }
    },
    newRun() {
      if (state.busy) return;
      onNew();
      update({ draftVersion: state.draftVersion + 1 });
      selection++;
      disconnect?.();
      update({ run: null, progress: null, connected: false, error: '' });
      route();
    },
    accept(run) {
      accept(run);
    },
    async act(action) {
      if (state.busy) return false;
      const current = epoch,
        selected = selection;
      update({ busy: true, error: '' });
      try {
        const run = await action();
        if (!alive || current !== epoch || selected !== selection) return false;
        const changed = state.run?.id !== run.id;
        update({ run: changed ? run : state.run });
        accept(run);
        route();
        if (changed) attach(run.id);
        return true;
      } catch (error) {
        if (alive && current === epoch) fail(error);
        return false;
      } finally {
        if (alive) update({ busy: false });
      }
    },
    async command(action, goal) {
      const run = state.run;
      if (!run) return false;
      return controller.act(() =>
        send(run.id, {
          request_id: crypto.randomUUID(),
          expected_goal_revision: run.goal_revision,
          expected_version: run.version,
          action,
          goal: action === 'revise' ? (goal ?? '') : null,
        }),
      );
    },
  };
  return controller;
}
