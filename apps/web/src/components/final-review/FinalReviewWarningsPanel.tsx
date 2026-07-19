"use client";

import { useT } from "../../lib/i18n";
import type { RenderOutput } from "../../types/final-review";
import { getRenderWarnings } from "../../lib/finalReviewState";

export function FinalReviewWarningsPanel({ render }: { render: RenderOutput }) {
  const t = useT();
  const warnings = getRenderWarnings(render);

  return (
    <section className="final-panel fr-warn" aria-label={t("finalReviewWarnings.title")}>
      <div className="fr-warn__head">
        <h2>{t("finalReviewWarnings.title")}</h2>
        <span className={`pill ${warnings.length > 0 ? "warn" : "good"}`}>{warnings.length}</span>
      </div>
      {render.error_message ? <p className="warning-line danger">{render.error_message}</p> : null}
      {warnings.length === 0 ? (
        <p className="muted fr-warn__empty">{t("finalReviewWarnings.noWarnings")}</p>
      ) : (
        <ul className="fr-warn__list">
          {warnings.map((warning) => (
            <li key={warning} title={warning}>
              {warning}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
