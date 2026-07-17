"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { acceptInvite } from "../../../lib/api";
import { useAuth } from "../../../lib/auth";
import { sanitizeNextPath } from "../../../lib/authPaths";
import { useT } from "../../../lib/i18n";

export default function AcceptInvitePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setSession, refreshMe } = useAuth();
  const t = useT();
  const [inviteToken, setInviteToken] = useState(searchParams.get("token") ?? "");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const response = await acceptInvite({
        inviteToken,
        password,
        displayName: displayName || undefined
      });
      setSession(response.accessToken, response.refreshToken, "operator");
      await refreshMe();
      router.replace(sanitizeNextPath(searchParams.get("next"), "/"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.inviteFailed"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="invite-title">
        <p className="eyebrow">{t("auth.inviteEyebrow")}</p>
        <h1 id="invite-title">{t("auth.inviteTitle")}</h1>
        <p className="auth-copy">{t("auth.inviteCopy")}</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            {t("auth.inviteToken")}
            <input
              required
              minLength={16}
              value={inviteToken}
              onChange={(event) => setInviteToken(event.target.value)}
            />
          </label>
          <label>
            {t("auth.displayName")}
            <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
          <label>
            {t("auth.password")}
            <input
              autoComplete="new-password"
              minLength={8}
              required
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          <button className="primary" disabled={isSubmitting} type="submit">
            {isSubmitting ? t("auth.acceptingInvite") : t("auth.acceptInvite")}
          </button>
        </form>
        <p className="auth-switch">
          {t("auth.haveAccount")} <Link href="/auth/login">{t("auth.signInLink")}</Link>
        </p>
      </section>
    </main>
  );
}
