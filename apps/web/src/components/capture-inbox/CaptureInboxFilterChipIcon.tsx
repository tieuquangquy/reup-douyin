export type CaptureInboxFilterChipIconKind =
  | "time-week"
  | "time-month"
  | "time-current-month"
  | "perf-views"
  | "perf-engagement"
  | "perf-rates"
  | "meta-complete"
  | "meta-posted"
  | "meta-thumb"
  | "meta-duration"
  | "meta-views"
  | "meta-metrics"
  | "meta-actionable"
  | "lane-captured"
  | "lane-metadata-health"
  | "stat-comments"
  | "stat-shares";

type Props = {
  className?: string;
  kind: CaptureInboxFilterChipIconKind;
};

export function CaptureInboxFilterChipIcon({ className = "capture-inbox-filter-chip-icon__glyph", kind }: Props) {
  if (kind === "time-week") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M7.2 4.4h9.6c.8 0 1.4.6 1.4 1.4v12.4c0 .8-.6 1.4-1.4 1.4H7.2c-.8 0-1.4-.6-1.4-1.4V5.8c0-.8.6-1.4 1.4-1.4Zm.8 2.2v1.1h7.2V6.6H8Zm8.4 2.3H7.2v9.3h9.6V8.9Zm-7.2 1.8a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8Zm2.4 0a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8Zm2.4 0a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8Zm-4.8 2.4a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8Zm2.4 0a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8Zm2.4 0a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "time-month") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M7.2 4.4h9.6c.8 0 1.4.6 1.4 1.4v12.4c0 .8-.6 1.4-1.4 1.4H7.2c-.8 0-1.4-.6-1.4-1.4V5.8c0-.8.6-1.4 1.4-1.4Zm.8 2.2v1.1h7.2V6.6H8Zm8.4 2.3H7.2v9.3h9.6V8.9Zm-1.8 1.8a1.8 1.8 0 1 1 0 3.6 1.8 1.8 0 0 1 0-3.6Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "time-current-month") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M7.2 4.4h9.6c.8 0 1.4.6 1.4 1.4v12.4c0 .8-.6 1.4-1.4 1.4H7.2c-.8 0-1.4-.6-1.4-1.4V5.8c0-.8.6-1.4 1.4-1.4Zm.8 2.2v1.1h7.2V6.6H8Zm8.4 2.3H7.2v9.3h9.6V8.9Zm-8.4 1.8h9.6v2.4H7.2v-2.4Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "perf-views") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M12 5.2c4.1 0 7.8 2.5 9.4 6.3a1 1 0 0 1 0 .9C19.8 16.3 16.1 18.8 12 18.8S4.2 16.3 2.6 12.4a1 1 0 0 1 0-.9C4.2 7.7 7.9 5.2 12 5.2Zm0 2.2a5.4 5.4 0 1 0 0 10.8 5.4 5.4 0 0 0 0-10.8Zm0 2.2a3.2 3.2 0 1 1 0 6.4 3.2 3.2 0 0 1 0-6.4Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "perf-engagement") {
    return (
      <svg aria-hidden="true" className={className} data-icon-style="tiktok-solid" viewBox="0 0 24 24">
        <path
          d="M12 21s-7.3-4.2-9.5-8.4C.5 8.8 2.5 4.2 6.7 3.7A5.7 5.7 0 0 1 12 6.5a5.7 5.7 0 0 1 5.3-2.8c4.2.5 6.2 5.1 4.2 8.9C19.3 16.8 12 21 12 21Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "perf-rates") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M7.4 6.2h9.2a1.4 1.4 0 0 1 1.4 1.4v1.8H6V7.6a1.4 1.4 0 0 1 1.4-1.4Zm-1.4 5.4h12v5.4a1.4 1.4 0 0 1-1.4 1.4H7.4a1.4 1.4 0 0 1-1.4-1.4v-5.4Zm3.6 1.6v3.6h3.6v-3.6H9.6Z"
          fill="currentColor"
        />
        <path
          d="M15.2 12.4h2.4l-2.8 3.4a.8.8 0 0 1-1.2 0l-1.4-1.7-1.8 2.1H8.8l2.6-3.1 1.4 1.7 2.4-2.9Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "meta-complete") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M12 3.8a8.2 8.2 0 1 1 0 16.4 8.2 8.2 0 0 1 0-16.4Zm3.7 5.5a1 1 0 0 0-1.4-.1l-4.1 3.7-1.5-1.5a1 1 0 1 0-1.4 1.4l2.2 2.2a1 1 0 0 0 1.4 0l4.8-4.4a1 1 0 0 0 0-1.3Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "meta-posted") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M7.2 5.2h9.6c.8 0 1.4.6 1.4 1.4v11.8c0 .8-.6 1.4-1.4 1.4H7.2c-.8 0-1.4-.6-1.4-1.4V6.6c0-.8.6-1.4 1.4-1.4Zm4.8 9.2a1.1 1.1 0 1 0 0-2.2 1.1 1.1 0 0 0 0 2.2Zm0-3.6a1.1 1.1 0 1 0 0-2.2 1.1 1.1 0 0 0 0 2.2Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "meta-thumb") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M5.8 5.8h12.4v12.4H5.8V5.8Zm1.6 1.6v7.4l2.6-2.4 2.2 2.1 3.4-4.1 2.6 3.2V7.4H7.4Z"
          fill="currentColor"
        />
        <path d="M9.2 9.6a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8Z" fill="currentColor" />
      </svg>
    );
  }

  if (kind === "meta-duration") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M12 4.2a7.8 7.8 0 1 1 0 15.6 7.8 7.8 0 0 1 0-15.6Zm0 2a.9.9 0 0 0-.9.9v4.6l3.1 1.8a.9.9 0 1 0 .9-1.6l-2.6-1.5V7.1A.9.9 0 0 0 12 6.2Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "meta-views") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M12 6.4c3.4 0 6.5 2 7.8 5.1a.8.8 0 0 1 0 .6C18.5 15.2 15.4 17.2 12 17.2s-6.5-2-7.8-5.1a.8.8 0 0 1 0-.6C5.5 8.4 8.6 6.4 12 6.4Zm0 2a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2Z"
          fill="currentColor"
        />
        <path d="M5.2 5.2 18.8 18.8" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    );
  }

  if (kind === "meta-metrics") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path d="M6.2 17.8V10.2h3.6v7.6H6.2Zm4.8-4.8v4.8h3.6V13H11Zm4.8 2.4v2.4h3.6v-2.4h-3.6Z" fill="currentColor" />
      </svg>
    );
  }

  if (kind === "lane-captured") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M6.4 5.4h11.2c.8 0 1.4.6 1.4 1.4v11.4c0 .8-.6 1.4-1.4 1.4H6.4c-.8 0-1.4-.6-1.4-1.4V6.8c0-.8.6-1.4 1.4-1.4Zm1.6 1.6v9.2h8V7H8Zm4 1.8 2.8 2.8H9.2L12 9.4l1 1V8.4h2.2v2l-1 1Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "lane-metadata-health") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M5.8 6.4h5.6v5.6H5.8V6.4Zm7.2 0h5.6v5.6h-5.6V6.4Zm-7.2 7.2h5.6v5.6H5.8v-5.6Zm7.2 0h5.6v5.6h-5.6v-5.6Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "stat-comments") {
    return (
      <svg aria-hidden="true" className={className} data-icon-style="tiktok-solid" viewBox="0 0 24 24">
        <path
          d="M12 3.1c5.2 0 9.4 3.7 9.4 8.3 0 4.5-4.2 8.2-9.4 8.2-.9 0-1.8-.1-2.6-.3l-3.8 1.6c-.7.3-1.4-.4-1.1-1.1l1.3-3.1a7.7 7.7 0 0 1-3.2-6.3c0-4.6 4.2-8.3 9.4-8.3Z"
          fill="currentColor"
        />
        <circle cx="8" cy="11.3" fill="#fff" r="1.05" />
        <circle cx="12" cy="11.3" fill="#fff" r="1.05" />
        <circle cx="16" cy="11.3" fill="#fff" r="1.05" />
      </svg>
    );
  }

  if (kind === "stat-shares") {
    return (
      <svg aria-hidden="true" className={className} data-icon-style="tiktok-solid" viewBox="0 0 24 24">
        <path
          d="m21.5 10-7.8-7.2v4.3C7.2 7.7 3.1 11.5 2.4 18.4c2.6-3.5 6-5.2 11.3-5V18l7.8-8Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
      <path
        d="M6.4 5.2h11.2l1.6 3.2 3.2.8-2.2 2.8.4 3.4-3.4-1.2-2.8 2.2-2.2-2.2-3.4 1.2.4-3.4-2.2-2.8 3.2-.8L6.4 5.2Z"
        fill="currentColor"
      />
    </svg>
  );
}
