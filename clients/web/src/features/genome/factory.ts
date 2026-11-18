import type { Asset, Project } from '../../shared/contracts';
import type { ApiClient } from '../../transport/ports';

export function createGenomeFeature(deps: { api: ApiClient }) {
  return {
    upload: async (project: string, file: File) => {
      if (file.size > 131072 || !file.size)
        throw new Error('请选择 1 至 131072 字节的 UTF-8 文本文件');
      const bytes = new Uint8Array(await file.arrayBuffer());
      const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
        .map((v) => v.toString(16).padStart(2, '0'))
        .join('');
      const intent = await deps.api.prepareUpload({
        request_id: crypto.randomUUID(),
        project_id: project,
        filename: file.name,
        size_bytes: file.size,
        sha256,
      });
      return deps.api.uploadContent(intent.id, bytes);
    },
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
