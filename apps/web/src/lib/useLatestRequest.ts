"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type LatestRequestToken = {
  id: number;
  signal: AbortSignal;
  isLatest: () => boolean;
};

export function createLatestRequestController() {
  let sequence = 0;
  let current: { id: number; controller: AbortController } | null = null;

  return {
    start(): LatestRequestToken {
      current?.controller.abort();
      const id = ++sequence;
      const controller = new AbortController();
      current = { id, controller };
      return {
        id,
        signal: controller.signal,
        isLatest: () => current?.id === id && !controller.signal.aborted,
      };
    },
    cancel() {
      current?.controller.abort();
      current = null;
    },
  };
}

export type LatestRequestMode = "initial" | "refresh";

export function useLatestRequest() {
  const controllerRef = useRef<ReturnType<typeof createLatestRequestController> | null>(null);
  if (!controllerRef.current) controllerRef.current = createLatestRequestController();
  const mountedRef = useRef(true);
  const [pendingMode, setPendingMode] = useState<LatestRequestMode | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      controllerRef.current?.cancel();
    };
  }, []);

  const run = useCallback(
    async <T,>(
      request: (signal: AbortSignal) => Promise<T>,
      onSuccess: (value: T) => void,
      mode: LatestRequestMode = "initial"
    ): Promise<T | undefined> => {
      const token = controllerRef.current!.start();
      setPendingMode(mode);
      setError(null);
      try {
        const value = await request(token.signal);
        if (!mountedRef.current || !token.isLatest()) return undefined;
        onSuccess(value);
        return value;
      } catch (reason) {
        if (reason instanceof DOMException && reason.name === "AbortError") return undefined;
        const nextError = reason instanceof Error ? reason : new Error(String(reason));
        if (mountedRef.current && token.isLatest()) setError(nextError);
        throw nextError;
      } finally {
        if (mountedRef.current && token.isLatest()) setPendingMode(null);
      }
    },
    []
  );

  const cancel = useCallback(() => {
    controllerRef.current?.cancel();
    if (mountedRef.current) setPendingMode(null);
  }, []);

  return {
    run,
    cancel,
    pending: pendingMode !== null,
    pendingMode,
    initialLoading: pendingMode === "initial",
    refreshing: pendingMode === "refresh",
    error,
  };
}
