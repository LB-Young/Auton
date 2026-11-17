import type { ApiClient } from '../../transport/ports';

export function createModelFeature(deps: { api: ApiClient }) {
  return {
    id: 'models',
    catalog: () => deps.api.models(),
    probe: (modelId: string, requestId: string) => deps.api.probeModel(modelId, requestId),
  };
}

export type ModelFeature = ReturnType<typeof createModelFeature>;
