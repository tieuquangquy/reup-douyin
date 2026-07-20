"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { AuthErrorBanner } from "../../../../components/auth/AuthErrorBanner";
import { loginWithPassword } from "../../../../lib/api";
import { useAuth } from "../../../../lib/auth";
import { isDevAuthPrefillEnabled, sanitizeNextPath } from "../../../../lib/authPaths";
import { useT } from "../../../../lib/i18n";

const DEV_PREFILL = isDevAuthPrefillEnabled();

export default function OpsLoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setSession, refreshMe } = useAuth();
  const t = useT();
  const [email, setEmail] = useState(DEV_PREFILL ? "admin@local.test" : "");
  const [password, setPassword] = useState(DEV_PREFILL ? "LocalAdmin!23456" : "");
  const [workspaceSlug, setWorkspaceSlug] = useState(DEV_PREFILL ? "local" : "local");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const errorCopy = {
    title: t("auth.opsLoginFailed"),
    serverUnavailable: t("auth.errorServerUnavailable"),
    unauthorized: t("auth.errorUnauthorized"),
    forbidden: t("auth.errorForbidden"),
    network: t("auth.errorNetwork"),
    generic: t("auth.errorGeneric")
  };

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const response = await loginWithPassword({
        email,
        password,
        workspaceSlug,
        client: "ops"
      });
      setSession(response.accessToken, response.refreshToken, "ops");
      await refreshMe();
      router.replace(sanitizeNextPath(searchParams.get("next"), "/ops"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.opsLoginFailed"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-stage auth-stage--ops">
        <aside className="auth-brand auth-brand--ops">
          <img
            alt=""
            className="auth-brand__logo"
            height={44}
            src="/brand/logo-loop-r.svg"
            width={44}
          />
          <p className="auth-brand__title">{t("auth.opsLoginBrand")}</p>
          <p className="auth-brand__workflow">{t("auth.opsLoginWorkflow")}</p>
          <div className="auth-brand__visual">
            <img
              alt={t("auth.opsLoginVisualAlt")}
              className="auth-brand__art"
              height={360}
              src="/auth/ops-console-monitor.png"
              width={480}
            />
          </div>
          <p className="auth-brand__copy">{t("auth.opsLoginCopy")}</p>
        </aside>
        <section className="auth-card" aria-labelledby="ops-login-title">
          <h1 id="ops-login-title">{t("auth.opsLoginTitle")}</h1>
          <p className="auth-copy auth-copy--compact">{t("auth.opsFormHint")}</p>
          <form className="auth-form" onSubmit={handleSubmit}>
            <label>
              {t("auth.email")}
              <input
                autoComplete="email"
                required
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              {t("auth.password")}
              <input
                autoComplete="current-password"
                minLength={8}
                required
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <label>
              {t("auth.workspaceSlug")}
              <input
                minLength={3}
                required
                value={workspaceSlug}
                onChange={(event) => setWorkspaceSlug(event.target.value)}
              />
            </label>
            {error ? <AuthErrorBanner raw={error} copy={errorCopy} /> : null}
            <button className="primary" disabled={isSubmitting} type="submit">
              {isSubmitting ? t("auth.signingIn") : t("auth.opsSignIn")}
            </button>
          </form>
          <p className="auth-switch">
            {t("auth.needOperatorStudio")}{" "}
            <Link href="/auth/login">{t("auth.signInLink")}</Link>
          </p>
        </section>
      </div>
    </main>
  );
}
