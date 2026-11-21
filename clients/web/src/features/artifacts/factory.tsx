import type { Artifact } from '../../shared/contracts';
import { Markdown } from '../../shared/Markdown';

export class ArtifactViewerFactory {
  create() {
    return {
      renderText(text: string) {
        return <Markdown>{text}</Markdown>;
      },
      id: 'artifacts',
      render(artifact: Artifact) {
        return <Markdown>{artifact.content}</Markdown>;
      },
    };
  }
}
export function createArtifactFeature() {
  return new ArtifactViewerFactory().create();
}
