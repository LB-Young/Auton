import type { ApiClient } from '../../transport/ports';
import type { RecoveryCommand } from '../../shared/contracts';

export function createExperienceFeature(deps: { api: ApiClient }) {
  return {
    id: 'experience',
    trajectory: (project: string, run: string) => deps.api.trajectory(project, run),
    recover: (project: string, run: string, command: RecoveryCommand) =>
      deps.api.recoverRun(project, run, command),
  };
}
export type ExperienceFeature = ReturnType<typeof createExperienceFeature>;
