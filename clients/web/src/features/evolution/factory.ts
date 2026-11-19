import type { ApiClient } from '../../transport/ports';
export class EvolutionFeatureFactory {
  create(deps: { api: ApiClient }) {
    return {
      api: deps.api.evolution,
      projects: () => deps.api.projects(),
      assets: (id: string) => deps.api.assets(id),
      reports: (id: string) => deps.api.assessment.reports(id),
      snapshot: (id: string) => deps.api.resolveAssets(id),
      bank: () => deps.api.assessment.bank(),
      models: () => deps.api.models(),
    };
  }
}
export type EvolutionFeature = ReturnType<EvolutionFeatureFactory['create']>;
