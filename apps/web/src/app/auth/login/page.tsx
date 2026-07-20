"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { AuthErrorBanner } from "../../../components/auth/AuthErrorBanner";
import { loginWithPassword } from "../../../lib/api";
import { useAuth } from "../../../lib/auth";
import { isDevAuthPrefillEnabled, sanitizeNextPath } from "../../../lib/authPaths";
import { useT } from "../../../lib/i18n";

const DEV_PREFILL = isDevAuthPrefillEnabled();

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setSession, refreshMe } = useAuth();
  const t = useT();
  const [email, setEmail] = useState(DEV_PREFILL ? "admin@local.test" : "");
  const [password, setPassword] = useState(DEV_PREFILL ? "LocalAdmin!23456" : "");
  const [workspaceSlug, setWorkspaceSlug] = useState(DEV_PREFILL ? "local-workspace" : "local");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const errorCopy = {
    title: t("auth.loginFailed"),
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
      const response = await loginWithPassword({ email, password, workspaceSlug, client: "operator" });
      setSession(response.accessToken, response.refreshToken, "operator");
      await refreshMe();
      router.replace(sanitizeNextPath(searchParams.get("next"), "/"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.loginFailed"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-stage">
        <aside className="auth-brand">
          <img
            alt=""
            className="auth-brand__logo"
            height={44}
            src="/brand/logo-loop-r.svg"
            width={44}
          />
          <p className="auth-brand__title">{t("auth.loginBrand")}</p>
          <p className="auth-brand__workflow">{t("auth.loginWorkflow")}</p>
          <div className="auth-brand__visual">
            <img
              alt={t("auth.loginVisualAlt")}
              className="auth-brand__art"
              height={360}
              src="/auth/operator-studio-pipeline.png"
              width={480}
            />
          </div>
          <p className="auth-brand__copy">{t("auth.loginCopy")}</p>
        </aside>
        <section className="auth-card" aria-labelledby="login-title">
          <h1 id="login-title">{t("auth.loginTitle")}</h1>
          <p className="auth-copy auth-copy--compact">{t("auth.loginFormHint")}</p>
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
              {isSubmitting ? t("auth.signingIn") : t("auth.signIn")}
            </button>
          </form>
          <p className="auth-switch">
            {t("auth.noAccount")} <Link href="/auth/register">{t("auth.registerLink")}</Link>
          </p>
        </section>
      </div>
    </main>
  );
}
