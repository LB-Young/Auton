import type { ApiClient } from '../../transport/ports';

export function createPolicyFeature(deps: { api: ApiClient }) {
  return {
    id: 'policy',
    preview(kind: 'private-remote' | 'tool-write') {
      return deps.api.preview({
        principal: { owner: 'preview', role: 'runtime' },
        goal_id: 'preview',
        goal_revision: 1,
        operation_id: 'preview',
        autonomy: 0,
        input_digest: '0'.repeat(64),
        action: kind === 'private-remote' ? 'model.generate' : 'tool.write',
        destination: kind === 'private-remote' ? 'remote' : 'local',
        provider: kind === 'private-remote' ? 'deepseek' : undefined,
        data_domain: 'local-only',
      });
    },
  };
}
