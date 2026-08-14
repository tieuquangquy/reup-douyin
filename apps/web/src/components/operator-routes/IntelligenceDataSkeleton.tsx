/** Shared cold-load skeletons for Intelligence data tabs. */
export function IntelligenceTableSkeleton({
  label,
  rows = 5,
  className = "",
}: {
  label: string;
  rows?: number;
  className?: string;
}) {
  return (
    <div aria-busy="true" aria-label={label} className={`pl-iq-data-skeleton is-table ${className}`.trim()}>
      <span className="visually-hidden">{label}</span>
      <div className="pl-iq-data-skeleton__head" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </div>
      {Array.from({ length: rows }, (_, index) => (
        <div className="pl-iq-data-skeleton__row" key={index} aria-hidden="true">
          <i className="is-thumb" />
          <i className="is-wide" />
          <i />
          <i className="is-narrow" />
        </div>
      ))}
    </div>
  );
}

export function IntelligenceTreeSkeleton({
  label,
  rows = 4,
  className = "",
}: {
  label: string;
  rows?: number;
  className?: string;
}) {
  return (
    <div aria-busy="true" aria-label={label} className={`pl-iq-data-skeleton is-tree ${className}`.trim()}>
      <span className="visually-hidden">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div className={`pl-iq-data-skeleton__row${index === 0 || index === 2 ? " is-root" : " is-child"}`} key={index} aria-hidden="true">
          <i className="is-icon" />
          <i className="is-wide" />
          <i className="is-chip" />
          <i className="is-chip" />
        </div>
      ))}
    </div>
  );
}

export function IntelligenceSpectrumSkeleton({ label, className = "" }: { label: string; className?: string }) {
  return (
    <section aria-busy="true" aria-label={label} className={`pl-iq-data-skeleton is-spectrum ${className}`.trim()}>
      <span className="visually-hidden">{label}</span>
      <div className="pl-iq-data-skeleton__spectrum" aria-hidden="true">
        <i className="is-donut" />
        <div className="pl-iq-data-skeleton__legend">
          <i />
          <i />
          <i />
          <i />
        </div>
        <div className="pl-iq-data-skeleton__bars">
          <i />
          <i />
          <i />
        </div>
      </div>
    </section>
  );
}

export function IntelligenceKpiSkeleton({
  label,
  cards = 5,
  className = "",
}: {
  label: string;
  cards?: number;
  className?: string;
}) {
  return (
    <section aria-busy="true" aria-label={label} className={`pl-iq-data-skeleton is-kpis ${className}`.trim()}>
      <span className="visually-hidden">{label}</span>
      <div className="pl-iq-data-skeleton__kpis" aria-hidden="true">
        {Array.from({ length: cards }, (_, index) => (
          <i key={index} />
        ))}
      </div>
    </section>
  );
}

/** Content Intelligence Publishing Settings cold-load: left stage panel + right form fields. */
export function IntelligenceSettingsStageSkeleton({ label, className = "" }: { label: string; className?: string }) {
  return (
    <div aria-busy="true" aria-label={label} className={`pl-iq-data-skeleton is-stage ${className}`.trim()}>
      <span className="visually-hidden">{label}</span>
      <aside className="pl-iq-data-skeleton__stage-panel" aria-hidden="true">
        <i className="is-title" />
        <i className="is-sub" />
        <i className="is-meter" />
        <i className="is-fact" />
        <i className="is-fact" />
        <i className="is-fact" />
      </aside>
      <div className="pl-iq-data-skeleton__stage-form" aria-hidden="true">
        <i className="is-tabs" />
        <i className="is-field" />
        <i className="is-field" />
        <i className="is-field is-wide" />
        <i className="is-field" />
        <i className="is-actions" />
      </div>
    </div>
  );
}

/** Affiliate Catalog cold-load: toolbar meta chips + table rows. */
export function IntelligenceCatalogWorksheetSkeleton({
  label,
  rows = 5,
  className = "",
}: {
  label: string;
  rows?: number;
  className?: string;
}) {
  return (
    <div aria-busy="true" aria-label={label} className={`pl-iq-data-skeleton is-catalog-worksheet ${className}`.trim()}>
      <span className="visually-hidden">{label}</span>
      <div className="pl-iq-data-skeleton__catalog-toolbar" aria-hidden="true">
        <div className="pl-iq-data-skeleton__catalog-meta">
          <i className="is-fact" />
          <i className="is-fact" />
          <i className="is-fact" />
          <i className="is-version" />
        </div>
        <div className="pl-iq-data-skeleton__catalog-controls">
          <i className="is-search" />
          <i className="is-icon-btn" />
          <i className="is-icon-btn" />
          <i className="is-icon-btn" />
        </div>
      </div>
      <div className="pl-iq-data-skeleton__catalog-table" aria-hidden="true">
        <div className="pl-iq-data-skeleton__head">
          <i />
          <i />
          <i />
          <i />
        </div>
        {Array.from({ length: rows }, (_, index) => (
          <div className="pl-iq-data-skeleton__row" key={index}>
            <i className="is-thumb" />
            <i className="is-wide" />
            <i />
            <i className="is-narrow" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Affiliate Comments cold-load: left list cards + right editor fields. */
export function IntelligenceSplitEditorSkeleton({
  label,
  cards = 4,
  className = "",
}: {
  label: string;
  cards?: number;
  className?: string;
}) {
  return (
    <div aria-busy="true" aria-label={label} className={`pl-iq-data-skeleton is-split ${className}`.trim()}>
      <span className="visually-hidden">{label}</span>
      <aside className="pl-iq-data-skeleton__split-list" aria-hidden="true">
        <i className="is-header" />
        {Array.from({ length: cards }, (_, index) => (
          <i className="is-card" key={index} />
        ))}
      </aside>
      <div className="pl-iq-data-skeleton__split-editor" aria-hidden="true">
        <i className="is-title" />
        <i className="is-field" />
        <i className="is-textarea" />
        <i className="is-field" />
        <i className="is-field" />
        <i className="is-actions" />
      </div>
    </div>
  );
}
