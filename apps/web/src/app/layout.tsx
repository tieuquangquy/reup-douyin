import type { Metadata } from "next";
import { AuthProvider } from "../lib/auth";
import { I18nProvider } from "../lib/i18n";
import { rootMetadata } from "../lib/pageMetadata";
import { NoticeProvider } from "../components/shared/NoticeCenter";
import "./globals.css";

export const metadata: Metadata = rootMetadata;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Preload Regular only — Medium/Bold stay full face but load on demand (~500KB less on critical path). */}
        <link
          rel="preload"
          href="/fonts/google-sans/GoogleSans-Regular.woff2"
          as="font"
          type="font/woff2"
          crossOrigin="anonymous"
        />
      </head>
      <body suppressHydrationWarning>
        <I18nProvider>
          <NoticeProvider>
            <AuthProvider>{children}</AuthProvider>
          </NoticeProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
