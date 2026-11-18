import type { ApiClient } from '../../transport/ports';

export class DelegationFeatureFactory {
  create(deps: { api: ApiClient }) {
    return {
      api: deps.api.delegation,
      projects: () => deps.api.projects(),
      models: () => deps.api.models(),
      workspaces: () => deps.api.toolWorkspaces(),
      baseline: (id: string) => deps.api.agentRun(id),
    };
  }
}
export type DelegationFeature = ReturnType<DelegationFeatureFactory['create']>;
