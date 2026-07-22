"use client";

import { useT } from "../../lib/i18n";
import { TopbarLabeledButton } from "./TopbarLabeledButton";

function RefreshIcon() {
  return (
    <span aria-hidden="true" className="app-topbar-refresh-icon app-topbar-btn__glyph">
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
    <TopbarLabeledButton
      busy={busy}
      disabled={disabled}
      icon={<RefreshIcon />}
      label={label}
      onClick={onClick}
      title={label}
    />
  );
}
