"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

export type NoticeTone = "success" | "info" | "warning" | "error";

export type AppNotice = {
  id: string;
  message: string;
  tone: NoticeTone;
  createdAt: number;
};

type NoticeInput = {
  id?: string;
  message: string;
  tone?: NoticeTone;
  durationMs?: number | null;
};

type NoticeContextValue = {
  notices: AppNotice[];
  notify: (notice: NoticeInput) => string;
  dismiss: (id: string) => void;
  clear: () => void;
};

export const DEFAULT_NOTICE_DURATION_MS = 5000;
const MAX_VISIBLE_NOTICES = 4;
const NoticeContext = createContext<NoticeContextValue | null>(null);

export function upsertNotice(current: AppNotice[], notice: AppNotice): AppNotice[] {
  return [...current.filter((item) => item.id !== notice.id), notice].slice(-MAX_VISIBLE_NOTICES);
}

export function NoticeProvider({ children }: { children: ReactNode }) {
  const [notices, setNotices] = useState<AppNotice[]>([]);
  const timersRef = useRef<Map<string, number>>(new Map());
  const sequenceRef = useRef(0);

  const dismiss = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer !== undefined) window.clearTimeout(timer);
    timersRef.current.delete(id);
    setNotices((current) => current.filter((notice) => notice.id !== id));
  }, []);

  const clear = useCallback(() => {
    for (const timer of timersRef.current.values()) window.clearTimeout(timer);
    timersRef.current.clear();
    setNotices([]);
  }, []);

  const notify = useCallback((input: NoticeInput) => {
    const id = input.id ?? `notice-${Date.now()}-${++sequenceRef.current}`;
    const tone = input.tone ?? "info";
    const notice: AppNotice = { id, message: input.message, tone, createdAt: Date.now() };
    setNotices((current) => upsertNotice(current, notice));

    const existingTimer = timersRef.current.get(id);
    if (existingTimer !== undefined) window.clearTimeout(existingTimer);
    const durationMs = input.durationMs ?? (tone === "success" || tone === "info" ? DEFAULT_NOTICE_DURATION_MS : null);
    if (durationMs && durationMs > 0) {
      timersRef.current.set(id, window.setTimeout(() => dismiss(id), durationMs));
    }
    return id;
  }, [dismiss]);

  useEffect(() => () => {
    for (const timer of timersRef.current.values()) window.clearTimeout(timer);
    timersRef.current.clear();
  }, []);

  const value = useMemo(() => ({ notices, notify, dismiss, clear }), [clear, dismiss, notices, notify]);
  return <NoticeContext.Provider value={value}>{children}</NoticeContext.Provider>;
}

export function useNotice() {
  const context = useContext(NoticeContext);
  if (!context) throw new Error("useNotice must be used within NoticeProvider");
  return context;
}

function NoticeIcon({ tone }: { tone: NoticeTone }) {
  if (tone === "success") return <path d="m5 10 3 3 7-7" />;
  if (tone === "error") return <path d="M10 5.5v5M10 14h.01" />;
  if (tone === "warning") return <path d="M10 4.5 16 15H4L10 4.5Zm0 3v3.5M10 13.5h.01" />;
  return <path d="M10 8.5V14M10 6h.01" />;
}

export function InlineNotice({
  message,
  tone = "info",
  title,
  onDismiss,
}: {
  message: string;
  tone?: NoticeTone;
  title?: string;
  onDismiss?: () => void;
}) {
  return (
    <section className={`app-inline-notice is-${tone}`} role={tone === "error" ? "alert" : "status"}>
      <span aria-hidden="true" className="app-inline-notice__icon">
        <svg viewBox="0 0 20 20"><NoticeIcon tone={tone} /></svg>
      </span>
      <div>
        {title ? <strong>{title}</strong> : null}
        <p>{message}</p>
      </div>
      {onDismiss ? (
        <button aria-label="Dismiss notification" onClick={onDismiss} title="Dismiss" type="button">
          <svg aria-hidden="true" viewBox="0 0 20 20"><path d="m6.5 6.5 7 7m0-7-7 7" /></svg>
        </button>
      ) : null}
    </section>
  );
}

export function NoticeViewport() {
  const { notices, dismiss } = useNotice();
  if (!notices.length) return null;

  return (
    <div aria-label="Notifications" className="app-notice-viewport">
      {notices.map((notice) => (
        <section
          aria-live={notice.tone === "error" ? "assertive" : "polite"}
          className={`app-notice is-${notice.tone}`}
          key={notice.id}
          role={notice.tone === "error" ? "alert" : "status"}
        >
          <span aria-hidden="true" className="app-notice__icon">
            <svg viewBox="0 0 20 20"><NoticeIcon tone={notice.tone} /></svg>
          </span>
          <p>{notice.message}</p>
          <button aria-label="Dismiss notification" onClick={() => dismiss(notice.id)} title="Dismiss" type="button">
            <svg aria-hidden="true" viewBox="0 0 20 20"><path d="m6.5 6.5 7 7m0-7-7 7" /></svg>
          </button>
        </section>
      ))}
    </div>
  );
}
