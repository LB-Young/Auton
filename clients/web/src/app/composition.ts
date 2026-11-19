import { EvolutionFeatureFactory } from '../features/evolution/factory';
import { DelegationFeatureFactory } from '../features/delegation/factory';
import { AssessmentFeatureFactory } from '../features/assessment/factory';
import { createProjectsFeature } from '../features/projects/factory';
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
  const projects = createProjectsFeature({ api });
  const events = new EventStreamFactory().create();
  return {
    projects,
    assessment: new AssessmentFeatureFactory().create({ api }),
    evolution: new EvolutionFeatureFactory().create({ api }),
    delegation: new DelegationFeatureFactory().create({ api }),
    chat: createChatFeature({ api, events }),
    judgment: createJudgmentFeature({ api }),
    tools: createToolsFeature({ api }),
    genome: createGenomeFeature({ api }),
    context: createContextFeature({ api }),
    agent: createAgentFeature({ api, projects, events: new RunEventStreamFactory().create() }),
    adoptLegacy: (project: string) => api.adoptLegacy(project),
    resetIdentity: () => api.resetIdentity(),
    experience: createExperienceFeature({ api }),
    models: createModelFeature({ api }),
    policy: createPolicyFeature({ api }),
    artifacts: createArtifactFeature(),
  };
}

export type Application = ReturnType<typeof createApplication>;

export class WebAppFactory {
  create(): Application {
    return createApplication();
  }
}
