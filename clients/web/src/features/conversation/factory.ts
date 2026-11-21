import type { ApiClient } from '../../transport/ports';
import { createConversationController } from './controller';
export class ConversationFeatureFactory {
  create({ api }: { api: ApiClient }) {
    return {
      controller: createConversationController(api),
      historyPath: (id: string) => api.conversations.exportHistory(id),
      directories: (path?: string) => api.localDirectories(path),
      artifact: (url: string) => api.artifactText(url),
    };
  }
}
export type ConversationFeature = ReturnType<ConversationFeatureFactory['create']>;
