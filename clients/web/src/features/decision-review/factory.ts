import type { ApiClient } from '../../transport/ports';
export class DecisionReviewFeatureFactory {
  create(deps: { api: ApiClient }) {
    return {
      api: deps.api.decisionReview,
      projects: () => deps.api.projects(),
      runs: (id: string) => deps.api.agentRuns(id),
      reports: (id: string) => deps.api.assessment.reports(id),
    };
  }
}
export type DecisionReviewFeature = ReturnType<DecisionReviewFeatureFactory['create']>;
