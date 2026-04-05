import { useEffect, useRef, useCallback } from 'react';

export interface TaskStatusEvent {
  type: 'task_status';
  task_id: string;
  status: string;
  workspace_id: string;
}

type EventHandler = (event: TaskStatusEvent) => void;

const WS_URL = (() => {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws/events`;
})();

const RECONNECT_DELAY_MS = 3000;

export function useTaskEvents(onEvent: EventHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef(false);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  const connect = useCallback(() => {
    if (unmountedRef.current) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'task_status') {
          handlerRef.current(data as TaskStatusEvent);
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      if (unmountedRef.current) return;
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    unmountedRef.current = false;
    connect();
    return () => {
      unmountedRef.current = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
