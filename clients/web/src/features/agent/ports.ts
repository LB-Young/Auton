import type {
  AgentRun,
  ModelInfo,
  Project,
  RunSnapshot,
  WorkspaceView,
  RunCommand,
} from '../../shared/contracts';
export interface AgentSnapshot {
  draftVersion: number;
  projects: Project[];
  workspaces: WorkspaceView[];
  models: ModelInfo[];
  project: string;
  runs: AgentRun[];
  run: AgentRun | null;
  next: number | null;
  search: string;
  loading: boolean;
  busy: boolean;
  connected: boolean;
  error: string;
  progress: RunSnapshot['transient'];
}
export interface AgentController {
  subscribe(listener: () => void): () => void;
  getSnapshot(): AgentSnapshot;
  start(): Promise<void>;
  dispose(): void;
  project(id: string): Promise<void>;
  search(text: string): Promise<void>;
  more(): Promise<void>;
  select(id: string): Promise<void>;
  newRun(): void;
  accept(run: AgentRun): void;
  act(action: () => Promise<AgentRun>): Promise<boolean>;
  command(action: RunCommand['action'], goal?: string): Promise<boolean>;
}
