"use client";

import { useLocale, useSetLocale, SUPPORTED_LOCALES, type Locale } from "../../lib/i18n";

const COMPACT_LOCALES = ["vi", "en"] as const satisfies readonly Locale[];

export function LanguageSwitcher() {
  const locale = useLocale();
  const setLocale = useSetLocale();

  return (
    <div aria-label="Switch language" className="language-switcher is-segmented" role="group">
      {COMPACT_LOCALES.map((value) => {
        const option = SUPPORTED_LOCALES.find((candidate) => candidate.value === value);
        return (
          <button
            aria-label={`Switch to ${option?.label ?? value.toUpperCase()}`}
            aria-pressed={locale === value}
            className={locale === value ? "is-active" : ""}
            key={value}
            onClick={() => setLocale(value)}
            title={option?.label}
            type="button"
          >
            {value.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}
