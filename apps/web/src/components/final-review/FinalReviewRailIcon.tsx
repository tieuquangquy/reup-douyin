/** Compact rail-tab glyphs for Final Review workspace. */
export type FinalReviewRailIconKind = "review" | "visual" | "risk" | "info";

export function FinalReviewRailIcon({
  kind,
  className = "fr-rail__tab-icon"
}: {
  kind: FinalReviewRailIconKind;
  className?: string;
}) {
  if (kind === "review") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M6.2 4.6h11.6A1.6 1.6 0 0 1 19.4 6.2v11.6a1.6 1.6 0 0 1-1.6 1.6H6.2a1.6 1.6 0 0 1-1.6-1.6V6.2A1.6 1.6 0 0 1 6.2 4.6Zm2 3.2a.9.9 0 0 0 0 1.8h7.6a.9.9 0 1 0 0-1.8H8.2Zm0 3.6a.9.9 0 0 0 0 1.8h7.6a.9.9 0 1 0 0-1.8H8.2Zm0 3.6a.9.9 0 0 0 0 1.8h5.2a.9.9 0 1 0 0-1.8H8.2Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (kind === "visual") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M4.6 6.4h14.8A1.6 1.6 0 0 1 21 8v6.4a1.6 1.6 0 0 1-1.6 1.6h-5.2l2.2 2.4a.9.9 0 1 1-1.4 1.2L12.4 16H11.6l-2.6 3.6a.9.9 0 1 1-1.4-1.2l2.2-2.4H5.2A1.6 1.6 0 0 1 3.6 14.4V8A1.6 1.6 0 0 1 5.2 6.4Zm1.6 2v5.2h11.6V8.4H6.8Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  if (kind === "risk") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
        <path
          d="M12 3.4c.4 0 .8.2 1 .6l8.1 14.2a1.2 1.2 0 0 1-1 1.8H3.9a1.2 1.2 0 0 1-1-1.8L11 4c.2-.4.6-.6 1-.6Zm0 4.4a1 1 0 0 0-1 1v4.2a1 1 0 1 0 2 0V8.8a1 1 0 0 0-1-1Zm0 8.2a1.2 1.2 0 1 0 0 2.4 1.2 1.2 0 0 0 0-2.4Z"
          fill="currentColor"
        />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 24 24">
      <path
        d="M12 3.6a8.4 8.4 0 1 1 0 16.8 8.4 8.4 0 0 1 0-16.8Zm0 3.2a1.1 1.1 0 1 0 0 2.2 1.1 1.1 0 0 0 0-2.2Zm-1.2 4.2a1 1 0 0 1 1-1h.4a1 1 0 0 1 1 1v5.2a1 1 0 1 1-2 0v-5.2Z"
        fill="currentColor"
      />
    </svg>
  );
}
