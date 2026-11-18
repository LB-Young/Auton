import type { ApiClient } from '../../transport/ports';
import type { CreateRun, RunCommand } from '../../shared/contracts';

export function createAgentFeature(deps: { api: ApiClient }) {
  return {
    id: 'agent',
    projects: () => deps.api.projects(),
    workspaces: () => deps.api.toolWorkspaces(),
    models: () => deps.api.models(),
    list: (project: string) => deps.api.agentRuns(project),
    get: (id: string) => deps.api.agentRun(id),
    create: (command: CreateRun) => deps.api.createRun(command),
    command: (id: string, command: RunCommand) => deps.api.agentCommand(id, command),
  };
}
export type AgentFeature = ReturnType<typeof createAgentFeature>;
