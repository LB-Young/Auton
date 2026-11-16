import type { ApiClient, EventStream } from '../../transport/ports';
import { createChatController } from './controller';

export function createChatFeature(deps: { api: ApiClient; events: EventStream }) {
  return {
    id: 'chat',
    controller: createChatController(deps.api, deps.events),
    routes: ['/'],
    requiredCapability: 'demo',
  };
}
