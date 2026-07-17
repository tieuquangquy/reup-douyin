"use client";

import { useT } from "../../lib/i18n";
import type { RenderOutput } from "../../types/final-review";
import { getRenderWarnings } from "../../lib/finalReviewState";

export function FinalReviewWarningsPanel({ render }: { render: RenderOutput }) {
  const t = useT();
  const warnings = getRenderWarnings(render);

  return (
    <section className="final-panel">
      <div className="panel-heading">
        <h2>{t("finalReviewWarnings.title")}</h2>
        <span className={`pill ${warnings.length > 0 ? "warn" : "good"}`}>{warnings.length}</span>
      </div>
      {render.error_message ? <p className="warning-line danger">{render.error_message}</p> : null}
      {warnings.length === 0 ? (
        <p className="muted">{t("finalReviewWarnings.noWarnings")}</p>
      ) : (
        <ul className="warning-list">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
