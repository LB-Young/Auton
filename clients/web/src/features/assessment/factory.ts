import type { ApiClient } from '../../transport/ports';

export class AssessmentFeatureFactory {
  create(deps: { api: ApiClient }) {
    return {
      api: deps.api.assessment,
      projects: () => deps.api.projects(),
      history: (project: string, after: number) => deps.api.runHistory(project, after, ''),
      run: (id: string) => deps.api.agentRun(id),
    };
  }
}
export type AssessmentFeature = ReturnType<AssessmentFeatureFactory['create']>;
