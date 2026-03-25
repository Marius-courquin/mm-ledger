import { useEffect, useRef } from 'react';

type SSEHandlers = {
  onWorkerStatus?: (data: { connector_id: string; state: string; detail?: string }) => void;
  onBalanceUpdate?: (data: { account_id: string; total_value: number; updated_at: string }) => void;
  onPositionUpdate?: (data: { connector_id: string; account_id: string; symbol: string; current_price: number }) => void;
  onSnapshotComplete?: (data: { connector_id: string; date: string; status: string }) => void;
  onError?: (data: { connector_id: string; message: string }) => void;
};

export function useSSE(enabled: boolean, handlers: SSEHandlers) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!enabled) return;

    const es = new EventSource('/api/events', { withCredentials: true });

    es.addEventListener('worker_status', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      handlersRef.current.onWorkerStatus?.(data);
    });

    es.addEventListener('balance_update', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      handlersRef.current.onBalanceUpdate?.(data);
    });

    es.addEventListener('position_update', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      handlersRef.current.onPositionUpdate?.(data);
    });

    es.addEventListener('snapshot_complete', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      handlersRef.current.onSnapshotComplete?.(data);
    });

    es.addEventListener('error', (e: MessageEvent) => {
      if (e.data) {
        const data = JSON.parse(e.data);
        handlersRef.current.onError?.(data);
      }
    });

    return () => {
      es.close();
    };
  }, [enabled]);
}
