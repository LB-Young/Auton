import type {
  Bootstrap,
  Session,
  SessionEvent,
  ActionRequest,
  PolicyDecision,
} from '../shared/contracts';

export interface ApiClient {
  bootstrap(): Promise<Bootstrap>;
  preview(action: ActionRequest): Promise<PolicyDecision>;
  sessions(): Promise<Session[]>;
  create(requestId: string): Promise<Session>;
  send(id: string, content: string, requestId: string): Promise<Session>;
  stop(id: string, runId: string, requestId: string): Promise<Session>;
}

export interface EventStream {
  connect(
    sessionId: string,
    onSnapshot: (event: SessionEvent) => void,
    onConnection: (connected: boolean) => void,
  ): () => void;
}
