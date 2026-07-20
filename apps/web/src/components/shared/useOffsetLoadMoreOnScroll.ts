"use client";

import { useEffect, useRef, type RefObject } from "react";

type Options = {
  sentinelRef: RefObject<HTMLElement | null>;
  hasMore: boolean;
  loading: boolean;
  disabled?: boolean;
  onLoadMore?: () => void;
  /** Used to detect stalled pages (no new rows appended). */
  loadedCount?: number;
  /** Scroll container; omit for viewport (page scroll). */
  root?: Element | null;
  rootMargin?: string;
};

const RETRY_COOLDOWN_MS = 220;

function parseRootMarginPx(rootMargin: string): number {
  const match = rootMargin.match(/(-?\d+(?:\.\d+)?)px/);
  return match ? Number(match[1]) : 320;
}

function isSentinelNearViewport(
  sentinel: HTMLElement,
  root: Element | null,
  rootMargin: string
): boolean {
  const margin = parseRootMarginPx(rootMargin);
  const rect = sentinel.getBoundingClientRect();
  if (root instanceof Element) {
    const rootRect = root.getBoundingClientRect();
    return rect.top <= rootRect.bottom + margin && rect.bottom >= rootRect.top - margin;
  }
  return rect.top <= window.innerHeight + margin && rect.bottom >= -margin;
}

export function useOffsetLoadMoreOnScroll({
  sentinelRef,
  hasMore,
  loading,
  disabled = false,
  onLoadMore,
  loadedCount,
  root = null,
  rootMargin = "320px 0px",
}: Options) {
  const loadingRef = useRef(loading);
  const hasMoreRef = useRef(hasMore);
  const disabledRef = useRef(disabled);
  const onLoadMoreRef = useRef(onLoadMore);
  const pendingRef = useRef(false);
  const loadedCountAtRequestRef = useRef<number | null>(null);

  loadingRef.current = loading;
  hasMoreRef.current = hasMore;
  disabledRef.current = disabled;
  onLoadMoreRef.current = onLoadMore;

  const tryLoadMore = () => {
    if (pendingRef.current || loadingRef.current || disabledRef.current || !hasMoreRef.current) return;
    const load = onLoadMoreRef.current;
    if (!load) return;
    pendingRef.current = true;
    loadedCountAtRequestRef.current = loadedCount ?? null;
    load();
  };

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          tryLoadMore();
        }
      },
      { root, rootMargin }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [sentinelRef, hasMore, root, rootMargin]);

  useEffect(() => {
    if (loading) return;

    const startCount = loadedCountAtRequestRef.current;
    loadedCountAtRequestRef.current = null;
    const grew =
      startCount === null
      || loadedCount === undefined
      || loadedCount > startCount;

    if (!hasMore || disabled || !grew) {
      pendingRef.current = false;
      return;
    }

    const sentinel = sentinelRef.current;
    if (!sentinel) {
      pendingRef.current = false;
      return;
    }

    const timer = window.setTimeout(() => {
      pendingRef.current = false;
      if (loadingRef.current || disabledRef.current || !hasMoreRef.current) return;
      if (isSentinelNearViewport(sentinel, root, rootMargin)) {
        tryLoadMore();
      }
    }, RETRY_COOLDOWN_MS);

    return () => window.clearTimeout(timer);
  }, [loading, hasMore, disabled, loadedCount, root, rootMargin, sentinelRef]);
}
