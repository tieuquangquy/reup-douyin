/**
 * Work action icons — solid glyphs, distinct from Ops stroke set.
 * Each shape maps to the button verb at ~16px.
 */
export type WorkItemActionIconKind =
  | "promote"
  | "approve"
  | "send"
  | "details"
  | "later"
  | "reject"
  | "delete"
  | "recheck"
  | "open"
  | "dismiss"
  | "play"
  | "pause"
  | "transcript"
  | "retry"
  | "process";

type Props = {
  kind: WorkItemActionIconKind;
  className?: string;
};

export function WorkItemActionIcon({ kind, className = "review-board-tile-btn__icon" }: Props) {
  // Promote → lift up (arrow into tray)
  if (kind === "promote") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M11.2 15.2V8.6l-2.4 2.4a.9.9 0 1 1-1.3-1.3l4-4a.9.9 0 0 1 1.3 0l4 4a.9.9 0 1 1-1.3 1.3l-2.4-2.4v6.6a.9.9 0 0 1-1.8 0Z"
          fill="currentColor"
        />
        <path d="M5.5 18.2h13a1 1 0 1 1 0 2h-13a1 1 0 1 1 0-2Z" fill="currentColor" />
      </svg>
    );
  }

  // Send → share/forward into next lane
  if (kind === "send") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M8.2 6.2a2.2 2.2 0 1 1 0 4.4 2.2 2.2 0 0 1 0-4.4Zm7.6 3.2a2.2 2.2 0 1 1 0 4.4 2.2 2.2 0 0 1 0-4.4ZM8.2 13.4a2.2 2.2 0 1 1 0 4.4 2.2 2.2 0 0 1 0-4.4Z"
          fill="currentColor"
        />
        <path
          d="M9.9 9.4 14 11.1M9.9 14.6l4.1-1.7"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  // Open → expand / open window
  if (kind === "open") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M6 5.5h5.2a1 1 0 1 1 0 2H7.5v3.7a1 1 0 1 1-2 0V6.5A1 1 0 0 1 6 5.5Zm6.8 0H18a1 1 0 0 1 1 1v5.2a1 1 0 1 1-2 0V7.5h-3.2a1 1 0 1 1 0-2ZM5.5 12.8a1 1 0 0 1 1 1v3.2H9.7a1 1 0 1 1 0 2H6a1 1 0 0 1-1-1v-4.2a1 1 0 0 1 1-1Zm12 0a1 1 0 0 1 1 1v4.2a1 1 0 0 1-1 1h-4.2a1 1 0 1 1 0-2h3.2v-3.2a1 1 0 0 1 1-1Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  // Approve → check badge
  if (kind === "approve") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M12 3.8a8.2 8.2 0 1 1 0 16.4A8.2 8.2 0 0 1 12 3.8Zm3.7 5.5a1 1 0 0 0-1.4-.1l-4.1 3.7-1.5-1.5a1 1 0 1 0-1.4 1.4l2.2 2.2a1 1 0 0 0 1.4 0l4.8-4.4a1 1 0 0 0 0-1.3Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  // Details → stacked lines (inspect list)
  if (kind === "details") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M5.5 6.2h13a1.1 1.1 0 1 1 0 2.2h-13a1.1 1.1 0 1 1 0-2.2Zm0 4.7h13a1.1 1.1 0 1 1 0 2.2h-13a1.1 1.1 0 1 1 0-2.2Zm0 4.7h9.2a1.1 1.1 0 1 1 0 2.2H5.5a1.1 1.1 0 1 1 0-2.2Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  // Later → moon (snooze)
  if (kind === "later") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M14.2 4.6a.9.9 0 0 1 .9 1.2 7.2 7.2 0 0 0 7.1 9.4.9.9 0 0 1 .7 1.5A9.1 9.1 0 1 1 11.6 3.9a.9.9 0 0 1 2.6.7Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  // Reject → thumbs down
  if (kind === "reject") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M14.8 4.5H8.6a2.2 2.2 0 0 0-2.1 1.6L4.8 12a1.8 1.8 0 0 0 1.7 2.4h3.6l-.7 3.2a2.2 2.2 0 0 0 1.1 2.3l.5.3a1 1 0 0 0 1.4-.4l2.8-5.8h2.6A1.8 1.8 0 0 0 19.6 12V6.3a1.8 1.8 0 0 0-1.8-1.8h-3Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  // Dismiss → hide / fold away
  if (kind === "dismiss") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M12 13.8a1 1 0 0 1-.7-.3l-5-5a1 1 0 1 1 1.4-1.4L12 11.4l4.3-4.3a1 1 0 1 1 1.4 1.4l-5 5a1 1 0 0 1-.7.3Zm-5.7 3.4h11.4a1 1 0 1 1 0 2H6.3a1 1 0 1 1 0-2Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  // Delete → trash can
  if (kind === "delete") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M9.2 4.2h5.6c.5 0 .9.4.9.9V6h3.1a1 1 0 1 1 0 2h-.7l-.8 10.1A2.2 2.2 0 0 1 15.1 20H8.9a2.2 2.2 0 0 1-2.2-1.9L5.9 8H5.2a1 1 0 1 1 0-2h3.1V5.1c0-.5.4-.9.9-.9Zm1.1 1.8v.9h3.4V6h-3.4Zm-.4 4.2a1 1 0 0 0-1 1v5a1 1 0 1 0 2 0v-5a1 1 0 0 0-1-1Zm4.2 0a1 1 0 0 0-1 1v5a1 1 0 1 0 2 0v-5a1 1 0 0 0-1-1Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  // Recheck / retry → dual arrows (spin)
  if (kind === "recheck" || kind === "retry") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M7.2 7.6A7.2 7.2 0 0 1 18.4 10a1 1 0 1 0 2-.3 9.2 9.2 0 0 0-15.6-4.2L3.6 4.2a.9.9 0 0 0-1.5.8l.7 4.6a.9.9 0 0 0 1 .8l4.6-.7a.9.9 0 0 0-.3-1.8l-1-.1Zm9.6 8.8A7.2 7.2 0 0 1 5.6 14a1 1 0 1 0-2 .3 9.2 9.2 0 0 0 15.6 4.2l1.2 1.3a.9.9 0 0 0 1.5-.8l-.7-4.6a.9.9 0 0 0-1-.8l-4.6.7a.9.9 0 1 0 .3 1.8l.9.1Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (kind === "pause") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M8.2 5.5h2.2A1.5 1.5 0 0 1 11.9 7v10a1.5 1.5 0 0 1-1.5 1.5H8.2A1.5 1.5 0 0 1 6.7 17V7A1.5 1.5 0 0 1 8.2 5.5Zm5.4 0h2.2A1.5 1.5 0 0 1 17.3 7v10a1.5 1.5 0 0 1-1.5 1.5h-2.2A1.5 1.5 0 0 1 12.1 17V7a1.5 1.5 0 0 1 1.5-1.5Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  // Process / play → solid play
  if (kind === "play" || kind === "process") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path d="M8.2 5.8a1.2 1.2 0 0 1 1.8-.9l9.2 5.5a1.2 1.2 0 0 1 0 2.1l-9.2 5.5a1.2 1.2 0 0 1-1.8-1V5.8Z" fill="currentColor" />
      </svg>
    );
  }

  // Transcript → speech / captions
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
      <path
        d="M6.5 4.8h11A2.7 2.7 0 0 1 20.2 7.5v6.2a2.7 2.7 0 0 1-2.7 2.7h-3.1l-2.6 2.6a1 1 0 0 1-1.7-.7v-1.9H6.5A2.7 2.7 0 0 1 3.8 13.7V7.5A2.7 2.7 0 0 1 6.5 4.8Zm1.7 4.2a1 1 0 1 0 0 2h7.6a1 1 0 1 0 0-2H8.2Zm0 3.4a1 1 0 1 0 0 2h4.8a1 1 0 1 0 0-2H8.2Z"
        fill="currentColor"
      />
    </svg>
  );
}
