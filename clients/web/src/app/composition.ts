import { createArtifactFeature } from '../features/artifacts/factory';
import { createJudgmentFeature } from '../features/judgment/factory';
import { createToolsFeature } from '../features/tools/factory';
import { createExperienceFeature } from '../features/experience/factory';
import { createAgentFeature } from '../features/agent/factory';
import { createContextFeature } from '../features/context/factory';
import { createGenomeFeature } from '../features/genome/factory';
import { createModelFeature } from '../features/models/factory';
import { createPolicyFeature } from '../features/policy/factory';
import { createChatFeature } from '../features/chat/factory';
import { ApiClientFactory } from '../transport/api';
import { EventStreamFactory, RunEventStreamFactory } from '../transport/events';

export function createApplication() {
  const api = new ApiClientFactory().create();
  const events = new EventStreamFactory().create();
  return {
    chat: createChatFeature({ api, events }),
    judgment: createJudgmentFeature({ api }),
    tools: createToolsFeature({ api }),
    genome: createGenomeFeature({ api }),
    context: createContextFeature({ api }),
    agent: createAgentFeature({ api, events: new RunEventStreamFactory().create() }),
    adoptLegacy: (project: string) => api.adoptLegacy(project),
    resetIdentity: () => api.resetIdentity(),
    experience: createExperienceFeature({ api }),
    models: createModelFeature({ api }),
    policy: createPolicyFeature({ api }),
    artifacts: createArtifactFeature(),
  };
}

export type Application = ReturnType<typeof createApplication>;
