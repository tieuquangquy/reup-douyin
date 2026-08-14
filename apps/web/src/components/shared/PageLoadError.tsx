"use client";

import { useT } from "../../lib/i18n";

type PageLoadErrorProps = {
  title?: string;
  detail?: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
};

/**
 * Shared page-load failure card for operator routes.
 * Use inside AsyncContentBoundary errorState, or as OpsState's retry branch.
 */
export function PageLoadError({
  title,
  detail,
  onRetry,
  retryLabel,
  className = "",
}: PageLoadErrorProps) {
  const t = useT();
  return (
    <div className={`page-load-error ${className}`.trim()} role="alert">
      <h2 className="page-load-error__title">{title ?? t("common.couldNotLoadTitle")}</h2>
      <p className="page-load-error__detail">{detail ?? t("common.couldNotLoadDetail")}</p>
      {onRetry ? (
        <button className="page-load-error__retry" onClick={onRetry} type="button">
          {retryLabel ?? t("common.retry")}
        </button>
      ) : null}
    </div>
  );
}
