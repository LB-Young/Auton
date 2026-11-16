import type { Artifact } from '../../shared/contracts';
import { Markdown } from '../../shared/Markdown';

export function createArtifactFeature() {
  return {
    id: 'artifacts',
    render(artifact: Artifact) {
      return <Markdown>{artifact.content}</Markdown>;
    },
  };
}
