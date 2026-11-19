import type { ApiClient } from '../../transport/ports';
export class OperationsFeatureFactory {
  create(deps: { api: ApiClient }) {
    return { api: deps.api.operations, projects: () => deps.api.projects() };
  }
}
export type OperationsFeature = ReturnType<OperationsFeatureFactory['create']>;
