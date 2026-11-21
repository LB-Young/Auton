import type { ApiClient } from '../../transport/ports';
import { createConversationController } from './controller';
export class ConversationFeatureFactory {
  create({ api }: { api: ApiClient }) {
    return {
      controller: createConversationController(api),
      directories: (path?: string) => api.localDirectories(path),
      artifact: (url: string) => api.artifactText(url),
    };
  }
}
export type ConversationFeature = ReturnType<ConversationFeatureFactory['create']>;
