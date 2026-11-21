import type { AssetRevision, Project } from '../../shared/contracts';
export interface ProjectsPort {
  list(): Promise<Project[]>;
  create(project: Project): Promise<AssetRevision>;
}
