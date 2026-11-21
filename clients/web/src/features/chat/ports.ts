import type { Bootstrap, Session } from '../../shared/contracts';

export interface ChatSnapshot {
  boot: Bootstrap | null;
  sessions: Session[];
  selected: string | null;
  loading: boolean;
  posting: boolean;
  connected: boolean;
  error: string | null;
}

export interface ChatController {
  subscribe(listener: () => void): () => void;
  getSnapshot(): ChatSnapshot;
  start(): Promise<void>;
  dispose(): void;
  select(id: string): void;
  newSession(): Promise<void>;
  send(content: string): Promise<boolean>;
  stop(): Promise<void>;
  clearError(): void;
}
