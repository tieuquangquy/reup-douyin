"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode
} from "react";
import en from "./i18n/en.json";
import vi from "./i18n/vi.json";

export type Locale = "en" | "vi";

const dictionaries: Record<Locale, Record<string, unknown>> = { en, vi };

function getNestedValue(obj: Record<string, unknown>, path: string): string {
  const parts = path.split(".");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let current: any = obj;
  for (const part of parts) {
    if (current == null || typeof current !== "object") return path;
    current = current[part];
  }
  return typeof current === "string" ? current : path;
}

const STORAGE_KEY = "reup-douyin-locale";

type SetLocale = (locale: Locale) => void;

interface I18nContextValue {
  locale: Locale;
  setLocale: SetLocale;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function getInitialLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const stored = localStorage.getItem(STORAGE_KEY) as Locale | null;
  if (stored === "en" || stored === "vi") return stored;
  const browserLang = navigator.language.toLowerCase();
  if (browserLang.startsWith("vi")) return "vi";
  return "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    setLocaleState(getInitialLocale());
  }, []);

  const setLocale: SetLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    if (typeof window !== "undefined") {
      localStorage.setItem(STORAGE_KEY, newLocale);
      document.documentElement.lang = newLocale;
    }
  }, []);

  const t = useCallback(
    (key: string): string => {
      const dict = dictionaries[locale];
      return getNestedValue(dict, key);
    },
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useLocale(): Locale {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useLocale must be used within I18nProvider");
  return ctx.locale;
}

export function useSetLocale(): SetLocale {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useSetLocale must be used within I18nProvider");
  return ctx.setLocale;
}

/**
 * Translate a dot-notation key, e.g. t("nav.operatorStudio").
 * Falls back to the key itself when no translation is found.
 */
export function useT(): (key: string) => string {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useT must be used within I18nProvider");
  return ctx.t;
}

export const SUPPORTED_LOCALES: { value: Locale; label: string }[] = [
  { value: "en", label: "English" },
  { value: "vi", label: "Tiếng Việt" }
];
