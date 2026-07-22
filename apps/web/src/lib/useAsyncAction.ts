"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type AsyncDuplicatePolicy = "drop" | "replace";

export type AsyncActionGate = {
  run<T>(key: string, action: () => Promise<T> | T, policy?: AsyncDuplicatePolicy): Promise<T>;
  isPending(key: string): boolean;
  clear(): void;
};

export function createAsyncActionGate(): AsyncActionGate {
  const inFlight = new Map<string, Promise<unknown>>();

  return {
    run<T>(key: string, action: () => Promise<T> | T, policy: AsyncDuplicatePolicy = "drop"): Promise<T> {
      const existing = inFlight.get(key);
      if (existing && policy === "drop") return existing as Promise<T>;

      let task: Promise<T>;
      try {
        task = Promise.resolve(action());
      } catch (reason) {
        task = Promise.reject(reason);
      }
      const tracked = task.finally(() => {
        if (inFlight.get(key) === tracked) inFlight.delete(key);
      });
      inFlight.set(key, tracked);
      return tracked;
    },
    isPending(key: string) {
      return inFlight.has(key);
    },
    clear() {
      inFlight.clear();
    },
  };
}

export function useAsyncAction() {
  const gateRef = useRef<AsyncActionGate | null>(null);
  if (!gateRef.current) gateRef.current = createAsyncActionGate();
  const mountedRef = useRef(true);
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      gateRef.current?.clear();
    };
  }, []);

  const run = useCallback(
    <T,>(key: string, action: () => Promise<T> | T, policy: AsyncDuplicatePolicy = "drop"): Promise<T> => {
      const gate = gateRef.current!;
      if (!gate.isPending(key) || policy === "replace") {
        setPendingKeys((current) => new Set(current).add(key));
        setError(null);
      }
      return gate.run(key, action, policy).catch((reason: unknown) => {
        const nextError = reason instanceof Error ? reason : new Error(String(reason));
        if (mountedRef.current) setError(nextError);
        throw nextError;
      }).finally(() => {
        if (!mountedRef.current || gate.isPending(key)) return;
        setPendingKeys((current) => {
          const next = new Set(current);
          next.delete(key);
          return next;
        });
      });
    },
    []
  );

  const reset = useCallback(() => setError(null), []);
  const isPending = useCallback((key: string) => pendingKeys.has(key), [pendingKeys]);

  return {
    run,
    pending: pendingKeys.size > 0,
    pendingKey: pendingKeys.values().next().value as string | undefined,
    pendingKeys,
    isPending,
    error,
    reset,
  };
}
