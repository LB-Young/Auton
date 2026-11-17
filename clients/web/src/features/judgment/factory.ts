import type { ApiClient } from '../../transport/ports';

export function createJudgmentFeature(deps: { api: ApiClient }) {
  return {
    id: 'judgment',
    info: () => deps.api.judgment(),
    preview: (state: string, isPublic: boolean, requestId: string) =>
      deps.api.previewJudgment(state, isPublic, requestId),
  };
}
export type JudgmentFeature = ReturnType<typeof createJudgmentFeature>;
