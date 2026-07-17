"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
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
      <section className="auth-card" aria-labelledby="ops-login-title">
        <p className="eyebrow">{t("auth.opsEyebrow")}</p>
        <h1 id="ops-login-title">{t("auth.opsLoginTitle")}</h1>
        <p className="auth-copy">{t("auth.opsLoginCopy")}</p>
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
          {error ? (
            <p className="auth-error" role="alert">
              {error}
            </p>
          ) : null}
          <button className="primary" disabled={isSubmitting} type="submit">
            {isSubmitting ? t("auth.signingIn") : t("auth.opsSignIn")}
          </button>
        </form>
        <p className="auth-switch">
          {t("auth.needOperatorStudio")}{" "}
          <Link href="/auth/login">{t("auth.signInLink")}</Link>
        </p>
      </section>
    </main>
  );
}
