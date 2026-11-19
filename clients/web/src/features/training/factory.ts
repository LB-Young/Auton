import type { ApiClient } from '../../transport/ports';
export class ExecutorTrainingFeatureFactory {
  create(deps: { api: ApiClient }) {
    return { api: deps.api.training, projects: () => deps.api.projects() };
  }
}
export type TrainingFeature = ReturnType<ExecutorTrainingFeatureFactory['create']>;
