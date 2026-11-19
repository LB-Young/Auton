import type { ApiClient, DecisionTrainingApi } from '../../transport/ports';
export class ExecutorTrainingFeatureFactory {
  create(deps: { api: ApiClient }) {
    return {
      decisionApi: undefined as DecisionTrainingApi | undefined,
      api: deps.api.training,
      projects: () => deps.api.projects(),
    };
  }
}
export type TrainingFeature = ReturnType<ExecutorTrainingFeatureFactory['create']>;

export class DecisionTrainingFeatureFactory {
  create(deps: { api: ApiClient }) {
    return {
      api: deps.api.decisionTraining,
      decisionApi: deps.api.decisionTraining as DecisionTrainingApi | undefined,
      projects: () => deps.api.projects(),
    };
  }
}
