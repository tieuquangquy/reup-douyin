"use client";

import { useT } from "../../lib/i18n";

function RefreshIcon() {
  return (
    <span aria-hidden="true" className="app-topbar-refresh-icon">
      <svg fill="none" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M13.2 8A5.2 5.2 0 1 1 11.3 3.7M13.2 3.2v3.1h-3.1"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </svg>
    </span>
  );
}

export function TopbarRefreshButton({
  disabled,
  busy,
  onClick
}: {
  disabled?: boolean;
  busy?: boolean;
  onClick: () => void;
}) {
  const t = useT();
  const label = busy ? t("common.refreshing") : t("common.refresh");

  return (
    <button
      aria-busy={busy || undefined}
      aria-label={label}
      className={`app-topbar-btn is-icon${busy ? " is-busy" : ""}`}
      disabled={disabled || busy}
      onClick={onClick}
      title={label}
      type="button"
    >
      <RefreshIcon />
    </button>
  );
}
