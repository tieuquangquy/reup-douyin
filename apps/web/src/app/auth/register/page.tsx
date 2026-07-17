"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { registerWithPassword } from "../../../lib/api";
import { useAuth } from "../../../lib/auth";
import { isDevAuthPrefillEnabled, sanitizeNextPath } from "../../../lib/authPaths";
import { useT } from "../../../lib/i18n";

const DEV_PREFILL = isDevAuthPrefillEnabled();

export default function RegisterPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setSession, refreshMe } = useAuth();
  const t = useT();
  const [displayName, setDisplayName] = useState(DEV_PREFILL ? "Local Operator" : "");
  const [email, setEmail] = useState(DEV_PREFILL ? "operator@local.test" : "");
  const [password, setPassword] = useState(DEV_PREFILL ? "local-password" : "");
  const [workspaceSlug, setWorkspaceSlug] = useState(DEV_PREFILL ? "local-workspace" : "local");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const response = await registerWithPassword({ displayName, email, password, workspaceSlug });
      setSession(response.accessToken, response.refreshToken, "operator");
      await refreshMe();
      router.replace(sanitizeNextPath(searchParams.get("next"), "/"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.registerFailed"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="register-title">
        <p className="eyebrow">{t("auth.registerEyebrow")}</p>
        <h1 id="register-title">{t("auth.registerTitle")}</h1>
        <p className="auth-copy">{t("auth.registerCopy")}</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            {t("auth.displayName")}
            <input autoComplete="name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
          <label>
            {t("auth.email")}
            <input autoComplete="email" required type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            {t("auth.password")}
            <input autoComplete="new-password" minLength={8} required type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <label>
            {t("auth.workspaceSlug")}
            <input minLength={3} required value={workspaceSlug} onChange={(event) => setWorkspaceSlug(event.target.value)} />
          </label>
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          <button className="primary" disabled={isSubmitting} type="submit">
            {isSubmitting ? t("auth.registering") : t("auth.register")}
          </button>
        </form>
        <p className="auth-switch">
          {t("auth.haveAccount")} <Link href="/auth/login">{t("auth.signInLink")}</Link>
        </p>
      </section>
    </main>
  );
}
