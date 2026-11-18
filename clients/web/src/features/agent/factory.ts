import type { ApiClient, RunEventStream } from '../../transport/ports';
import type { CreateRun, RunCommand } from '../../shared/contracts';

export function createAgentFeature(deps: { api: ApiClient; events: RunEventStream }) {
  const pending = new Map<string, string>();
  async function stable<T extends { request_id: string }>(
    kind: string,
    command: T,
    send: (value: T) => Promise<import('../../shared/contracts').AgentRun>,
  ) {
    const key = kind + JSON.stringify({ ...command, request_id: '' });
    if (!pending.has(key) && pending.size >= 64)
      throw new Error('未确认命令过多，请刷新并核对任务历史');
    const request_id = pending.get(key) ?? command.request_id;
    pending.set(key, request_id);
    const result = await send({ ...command, request_id });
    pending.delete(key);
    return result;
  }
  return {
    id: 'agent',
    snapshot: (id: string) => deps.api.runSnapshot(id),
    subscribe: deps.events.connect,
    projects: () => deps.api.projects(),
    workspaces: () => deps.api.toolWorkspaces(),
    models: () => deps.api.models(),
    list: (project: string) => deps.api.agentRuns(project),
    get: (id: string) => deps.api.agentRun(id),
    create: (command: CreateRun) => stable('create', command, (value) => deps.api.createRun(value)),
    command: (id: string, command: RunCommand) =>
      stable(id, command, (value) => deps.api.agentCommand(id, value)),
  };
}
export type AgentFeature = ReturnType<typeof createAgentFeature>;
