import type { ApiClient } from '../../transport/ports';
import type { ContextPreviewCommand } from '../../shared/contracts';

export function createContextFeature(deps: { api: ApiClient }) {
  return {
    id: 'context',
    projects: () => deps.api.projects(),
    models: () => deps.api.models(),
    prepare: (project: string, command: ContextPreviewCommand) =>
      deps.api.prepareContext(project, command),
    snapshot: (project: string, id: string) => deps.api.contextSnapshot(project, id),
  };
}
export type ContextFeature = ReturnType<typeof createContextFeature>;
