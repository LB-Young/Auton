import type { ApiClient } from '../../transport/ports';
export class ReleaseFeatureFactory {
  create(deps: { api: ApiClient }) {
    return { api: deps.api.releases, projects: () => deps.api.projects() };
  }
}
export type ReleaseFeature = ReturnType<ReleaseFeatureFactory['create']>;
