import type { ProjectsPort } from '../projects/ports';
import type { ApiClient, RunEventStream } from '../../transport/ports';
import { createAgentController } from './controller';
import type { CreateRun, RunCommand } from '../../shared/contracts';

export function createAgentFeature(deps: {
  api: ApiClient;
  events: RunEventStream;
  projects: ProjectsPort;
}) {
  const draft = {
    workspace: '',
    model: '',
    goal: '',
    boundaries: '',
    kind: 'research' as 'research' | 'file',
    path: 'notes.md',
    content: '',
    isPublic: false,
  };
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
  const command = (id: string, value: RunCommand) =>
    stable(id, value, (body) => deps.api.agentCommand(id, body));
  return {
    draft,
    controller: createAgentController(deps.api, deps.events, command, deps.projects, () =>
      Object.assign(draft, {
        goal: '',
        content: '',
        boundaries: '',
        kind: 'research',
        path: 'notes.md',
        isPublic: false,
      }),
    ),
    feedback: (run: string, command: import('../../shared/contracts').FeedbackCommand) =>
      deps.api.feedback(run, command),
    preview: (url: string) => deps.api.artifactText(url),
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
