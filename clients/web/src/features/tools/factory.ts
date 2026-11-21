import type { ToolPrepareCommand } from '../../shared/contracts';
import type { ApiClient } from '../../transport/ports';

export function createToolsFeature(deps: { api: ApiClient }) {
  return {
    id: 'tools',
    catalog: () => deps.api.tools(),
    workspaces: () => deps.api.toolWorkspaces(),
    createWorkspace: (readOnly: boolean) =>
      deps.api.createToolWorkspace(crypto.randomUUID(), readOnly),
    prepare: (command: ToolPrepareCommand) => deps.api.prepareTool(command),
    approve: (id: string) => deps.api.approveTool(id),
    execute: (id: string, approvalId: string | null) => deps.api.executeTool(id, approvalId),
    reconcile: (id: string) => deps.api.reconcileTool(id),
    artifactUrl: (id: string) => `/api/v1/tools/operations/${encodeURIComponent(id)}/artifact`,
  };
}
export type ToolsFeature = ReturnType<typeof createToolsFeature>;
