"use client";

import { useLocale, useSetLocale, SUPPORTED_LOCALES, type Locale } from "../../lib/i18n";

function GlobeIcon() {
  return (
    <span aria-hidden="true" className="language-switcher__icon">
      <svg fill="none" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="8" r="5.25" stroke="currentColor" strokeWidth="1.4" />
        <path d="M2.75 8h10.5M8 2.75c1.6 1.7 2.4 3.4 2.4 5.25S9.6 11.55 8 13.25C6.4 11.55 5.6 9.85 5.6 8S6.4 4.45 8 2.75Z" stroke="currentColor" strokeWidth="1.4" />
      </svg>
    </span>
  );
}

export function LanguageSwitcher() {
  const locale = useLocale();
  const setLocale = useSetLocale();

  return (
    <div className="language-switcher">
      <label className="language-switcher__label" htmlFor="lang-select">
        <GlobeIcon />
      </label>
      <select
        id="lang-select"
        className="language-switcher__select"
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        aria-label="Switch language"
      >
        {SUPPORTED_LOCALES.map((l) => (
          <option key={l.value} value={l.value}>
            {l.label}
          </option>
        ))}
      </select>
    </div>
  );
}
