import type { Asset, Project } from '../../shared/contracts';
import type { ApiClient } from '../../transport/ports';

export function createGenomeFeature(deps: { api: ApiClient }) {
  return {
    projects: () => deps.api.projects(),
    create: (project: Project) => deps.api.createProject(project),
    view: (project: string) => deps.api.assets(project),
    propose: (project: string, asset: Asset, expected: string | null) =>
      deps.api.proposeAsset(project, asset, expected),
    change: (
      project: string,
      id: string,
      action: 'promote' | 'revoke' | 'rollback',
      expected: string,
      revision: string | null,
    ) => deps.api.changeAsset(project, id, action, expected, revision),
    history: (project: string, id: string) => deps.api.assetHistory(project, id),
    diff: (project: string, id: string, revision: string) =>
      deps.api.assetDiff(project, id, revision),
    resolve: (project: string) => deps.api.resolveAssets(project),
  };
}
export type GenomeFeature = ReturnType<typeof createGenomeFeature>;
