import { createArtifactFeature } from '../features/artifacts/factory';
import { createPolicyFeature } from '../features/policy/factory';
import { createChatFeature } from '../features/chat/factory';
import { ApiClientFactory } from '../transport/api';
import { EventStreamFactory } from '../transport/events';

export function createApplication() {
  const api = new ApiClientFactory().create();
  const events = new EventStreamFactory().create();
  return {
    chat: createChatFeature({ api, events }),
    policy: createPolicyFeature({ api }),
    artifacts: createArtifactFeature(),
  };
}

export type Application = ReturnType<typeof createApplication>;
