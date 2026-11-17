import { createArtifactFeature } from '../features/artifacts/factory';
import { createJudgmentFeature } from '../features/judgment/factory';
import { createModelFeature } from '../features/models/factory';
import { createPolicyFeature } from '../features/policy/factory';
import { createChatFeature } from '../features/chat/factory';
import { ApiClientFactory } from '../transport/api';
import { EventStreamFactory } from '../transport/events';

export function createApplication() {
  const api = new ApiClientFactory().create();
  const events = new EventStreamFactory().create();
  return {
    chat: createChatFeature({ api, events }),
    judgment: createJudgmentFeature({ api }),
    models: createModelFeature({ api }),
    policy: createPolicyFeature({ api }),
    artifacts: createArtifactFeature(),
  };
}

export type Application = ReturnType<typeof createApplication>;
