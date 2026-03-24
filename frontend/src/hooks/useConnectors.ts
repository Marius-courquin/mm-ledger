import { useEffect, useState, useCallback } from 'react';
import { getConnectors } from '@/api/connectors';
import type { Connector, WorkerState } from '@/lib/types';

export function useConnectors(vaultUnlocked: boolean) {
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const refreshConnectors = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await getConnectors();
      setConnectors(data);
    } catch {
      // On error (e.g. vault locked), leave current state
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (vaultUnlocked) {
      refreshConnectors();
    } else {
      setConnectors([]);
    }
  }, [vaultUnlocked, refreshConnectors]);

  const updateConnectorState = useCallback(
    (connectorId: string, state: string, detail?: string) => {
      setConnectors((prev) =>
        prev.map((c) => {
          if (c.id !== connectorId) return c;
          return {
            ...c,
            worker: {
              ...c.worker,
              state: state as WorkerState,
              detail,
            },
          };
        }),
      );
    },
    [],
  );

  return { connectors, updateConnectorState, refreshConnectors, isLoading };
}
