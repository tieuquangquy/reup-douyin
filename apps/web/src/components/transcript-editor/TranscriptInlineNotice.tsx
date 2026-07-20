"use client";

import { useEffect } from "react";
import { useT } from "../../lib/i18n";

type NoticeTone = "success" | "cancelled" | "error";

/** Success confirmations fade a bit sooner than cancelled FYI notices. */
export const TRANSCRIPT_SUCCESS_NOTICE_AUTO_DISMISS_MS = 5000;

/** Informational cancelled notices fade after a short read window. */
export const TRANSCRIPT_CANCELLED_NOTICE_AUTO_DISMISS_MS = 6000;

type Props = {
  tone: NoticeTone;
  children: string;
  onDismiss?: () => void;
  autoDismissMs?: number;
};

function NoticeIcon({ tone }: { tone: NoticeTone }) {
  if (tone === "success") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M5 10.2 8.2 13.4 15 6.6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (tone === "cancelled") {
    return (
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M7 10h6" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M10 6.5v5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="10" cy="14" r="0.9" fill="currentColor" />
    </svg>
  );
}

export function TranscriptInlineNotice({ tone, children, onDismiss, autoDismissMs }: Props) {
  const t = useT();

  useEffect(() => {
    if (!onDismiss || !autoDismissMs || autoDismissMs <= 0) return;
    const timer = window.setTimeout(onDismiss, autoDismissMs);
    return () => window.clearTimeout(timer);
  }, [onDismiss, autoDismissMs, children]);

  return (
    <div className={`transcript-inline-notice is-${tone}`} role="status">
      <span className="transcript-inline-notice__icon" aria-hidden="true">
        <NoticeIcon tone={tone} />
      </span>
      <p className="transcript-inline-notice__message">{children}</p>
      {onDismiss ? (
        <button
          type="button"
          className="transcript-inline-notice__dismiss"
          aria-label={t("common.close")}
          title={t("common.close")}
          onClick={onDismiss}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path
              d="M6.5 6.5 13.5 13.5M13.5 6.5 6.5 13.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
          </svg>
        </button>
      ) : null}
    </div>
  );
}
