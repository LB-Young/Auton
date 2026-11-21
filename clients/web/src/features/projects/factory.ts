import type { ApiClient } from '../../transport/ports';
import type { ProjectsPort } from './ports';
export function createProjectsFeature(deps: { api: ApiClient }): ProjectsPort {
  return { list: () => deps.api.projects(), create: (project) => deps.api.createProject(project) };
}
