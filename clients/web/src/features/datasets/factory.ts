import type { ApiClient } from '../../transport/ports';
export class DatasetsFeatureFactory {
  create(deps: { api: ApiClient }) {
    return {
      api: deps.api.datasets,
      projects: () => deps.api.projects(),
      runs: (project: string) => deps.api.agentRuns(project),
      reports: (project: string) => deps.api.assessment.reports(project),
    };
  }
}
export type DatasetsFeature = ReturnType<DatasetsFeatureFactory['create']>;
