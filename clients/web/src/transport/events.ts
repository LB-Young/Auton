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
