"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  fetchAuthMe,
  getApiAuthToken,
  getAuthSurface,
  logoutSession,
  persistAuthSession,
  setApiAuthToken,
  type AuthMeResponse,
  type AuthSurface
} from "./api";
import {
  isOpsConsolePath,
  loginPathForSurface,
  surfaceForPath,
  authenticatedLoginBounceTarget
} from "./authSurface";
import { useT } from "./i18n";

type AuthContextValue = {
  token: string | null;
  me: AuthMeResponse | null;
  surface: AuthSurface | null;
  isAuthenticated: boolean;
  isReady: boolean;
  setToken: (token: string | null) => void;
  setSession: (accessToken: string, refreshToken?: string | null, surface?: AuthSurface) => void;
  logout: () => void;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const PUBLIC_PATH_PREFIXES = ["/auth"];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATH_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

function AuthBootScreen({ message }: { message: string }) {
  return (
    <div className="auth-boot" role="status" aria-live="polite">
      <div className="auth-boot__card">
        <span className="auth-boot__spinner" aria-hidden="true" />
        <span className="auth-boot__brand">reup-douyin</span>
        <p className="auth-boot__message">{message}</p>
      </div>
    </div>
  );
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const t = useT();
  const [token, setTokenState] = useState<string | null>(null);
  const [me, setMe] = useState<AuthMeResponse | null>(null);
  const [surface, setSurface] = useState<AuthSurface | null>(null);
  const [isReady, setIsReady] = useState(false);

  const refreshMe = useCallback(async () => {
    const current = getApiAuthToken();
    if (!current) {
      setMe(null);
      return;
    }
    try {
      const profile = await fetchAuthMe();
      setMe(profile);
    } catch {
      setApiAuthToken(null);
      setTokenState(null);
      setSurface(null);
      setMe(null);
    }
  }, []);

  useEffect(() => {
    const existing = getApiAuthToken();
    setTokenState(existing);
    setSurface(getAuthSurface());
    if (!existing) {
      setIsReady(true);
      return;
    }
    setApiAuthToken(existing);
    void (async () => {
      try {
        const profile = await fetchAuthMe();
        setMe(profile);
      } catch {
        setApiAuthToken(null);
        setTokenState(null);
        setSurface(null);
        setMe(null);
      } finally {
        setIsReady(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!isReady || token || isPublicPath(pathname)) return;
    const needed = surfaceForPath(pathname);
    const next = encodeURIComponent(pathname);
    router.replace(`${loginPathForSurface(needed)}?next=${next}`);
  }, [isReady, pathname, router, token]);

  useEffect(() => {
    if (!isReady || !token || !surface) return;
    const loginBounce = authenticatedLoginBounceTarget(pathname, surface);
    if (loginBounce) {
      router.replace(loginBounce);
      return;
    }
    if (isPublicPath(pathname)) return;
    const pathSurface = surfaceForPath(pathname);
    if (pathSurface !== surface) {
      router.replace(loginPathForSurface(pathSurface));
    }
  }, [isReady, pathname, router, surface, token]);

  const setToken = useCallback((nextToken: string | null) => {
    setApiAuthToken(nextToken);
    setTokenState(nextToken && nextToken.trim() ? nextToken.trim() : null);
    if (!nextToken) {
      setMe(null);
      setSurface(null);
    }
  }, []);

  const setSession = useCallback(
    (accessToken: string, refreshToken?: string | null, nextSurface: AuthSurface = "operator") => {
      persistAuthSession(accessToken, refreshToken, nextSurface);
      setTokenState(accessToken.trim());
      setSurface(nextSurface);
    },
    []
  );

  const logout = useCallback(() => {
    const currentSurface = surface ?? getAuthSurface() ?? "operator";
    void (async () => {
      await logoutSession();
      setTokenState(null);
      setSurface(null);
      setMe(null);
      router.replace(loginPathForSurface(currentSurface));
    })();
  }, [router, surface]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      me,
      surface,
      isAuthenticated: Boolean(token),
      isReady,
      setToken,
      setSession,
      logout,
      refreshMe
    }),
    [isReady, logout, me, refreshMe, setSession, setToken, surface, token]
  );

  if (!isReady) {
    return <AuthBootScreen message={t("auth.loading")} />;
  }

  if (!token && !isPublicPath(pathname)) {
    return <AuthBootScreen message={t("auth.redirecting")} />;
  }

  if (token && surface && !isPublicPath(pathname) && surfaceForPath(pathname) !== surface) {
    return <AuthBootScreen message={t("auth.redirecting")} />;
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}

export { isOpsConsolePath };
