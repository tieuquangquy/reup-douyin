import { resolveAuthLoginError, type AuthLoginErrorCopy } from "../../lib/authLoginError";

type AuthErrorBannerProps = {
  raw: string;
  copy: AuthLoginErrorCopy;
};

export function AuthErrorBanner({ raw, copy }: AuthErrorBannerProps) {
  const view = resolveAuthLoginError(raw, copy);

  return (
    <div className="auth-error" role="alert">
      <span className="auth-error__icon" aria-hidden="true">
        <svg viewBox="0 0 20 20" width="20" height="20">
          <circle cx="10" cy="10" r="7.25" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path
            d="M10 6.4v4.2M10 13.1h.01"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <div className="auth-error__body">
        <strong className="auth-error__title">{view.title}</strong>
        <span className="auth-error__message">{view.message}</span>
      </div>
    </div>
  );
}
