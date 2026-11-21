import type { SessionEvent } from '../shared/contracts';
import type { EventStream } from './ports';

export class EventStreamFactory {
  create(): EventStream {
    return {
      connect(sessionId, onSnapshot, onConnection) {
        let disposed = false;
        let attempts = 0;
        let socket: WebSocket | undefined;
        let timer: ReturnType<typeof setTimeout> | undefined;
        const open = () => {
          if (disposed) return;
          const url = new URL(
            `/api/v1/sessions/${encodeURIComponent(sessionId)}/events`,
            window.location.origin,
          );
          url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
          socket = new WebSocket(url);
          socket.onopen = () => {
            attempts = 0;
            onConnection(true);
          };
          socket.onmessage = (message) => {
            try {
              const event = JSON.parse(String(message.data)) as SessionEvent;
              if (
                event.schema_version !== '1' ||
                event.session_id !== sessionId ||
                !event.payload ||
                !Number.isInteger(event.sequence)
              ) {
                socket?.close(1002, 'Unsupported event');
                return;
              }
              if (!disposed) onSnapshot(event);
            } catch {
              socket?.close(1002, 'Malformed event');
            }
          };
          socket.onerror = () => onConnection(false);
          socket.onclose = () => {
            if (disposed) return;
            onConnection(false);
            timer = setTimeout(open, Math.min(1000 * 2 ** attempts++, 10000));
          };
        };
        open();
        return () => {
          disposed = true;
          clearTimeout(timer);
          if (socket) {
            socket.onclose = null;
            socket.onmessage = null;
            socket.onerror = null;
            socket.onopen = null;
            socket.close();
          }
        };
      },
    };
  }
}

export class RunEventStreamFactory {
  create(): import('./ports').RunEventStream {
    return {
      connect(runId, onFrame, onConnection) {
        let disposed = false,
          cursor = 0,
          attempts = 0;
        let socket: WebSocket | undefined;
        let timer: ReturnType<typeof setTimeout> | undefined;
        const open = () => {
          if (disposed) return;
          const url = new URL(
            `/api/v1/agent/runs/${encodeURIComponent(runId)}/events`,
            window.location.origin,
          );
          url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
          url.searchParams.set('after', String(cursor));
          socket = new WebSocket(url);
          socket.onopen = () => {
            attempts = 0;
            onConnection(true);
          };
          socket.onmessage = (message) => {
            try {
              const frame = JSON.parse(
                String(message.data),
              ) as import('../shared/contracts').RunFrame;
              if (
                frame.schema_version !== 1 ||
                frame.run_id !== runId ||
                !Number.isSafeInteger(frame.cursor) ||
                frame.cursor < 0 ||
                !['snapshot', 'checkpoint', 'delta', 'heartbeat', 'reset_required'].includes(
                  frame.kind,
                )
              ) {
                socket?.close(1002);
                return;
              }
              if (frame.kind === 'reset_required') cursor = frame.cursor;
              else if (frame.persisted) cursor = Math.max(cursor, frame.cursor);
              if (!disposed) onFrame(frame);
            } catch {
              socket?.close(1002);
            }
          };
          socket.onerror = () => onConnection(false);
          socket.onclose = (event) => {
            if (disposed) return;
            onConnection(false);
            if (event.code !== 1008)
              timer = setTimeout(open, Math.min(1000 * 2 ** attempts++, 10000));
          };
        };
        open();
        return () => {
          disposed = true;
          clearTimeout(timer);
          if (socket) {
            socket.onclose = null;
            socket.onmessage = null;
            socket.onerror = null;
            socket.onopen = null;
            socket.close();
          }
        };
      },
    };
  }
}
