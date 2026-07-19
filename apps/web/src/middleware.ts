import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { SESSION_PRESENCE_COOKIE } from "./lib/authPaths";
import { loginPathForSurface, SESSION_SURFACE_COOKIE, surfaceForPath } from "./lib/authSurface";

const PUBLIC_PREFIXES = ["/auth"];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.get(SESSION_PRESENCE_COOKIE)?.value === "1";
  const surfaceCookie = request.cookies.get(SESSION_SURFACE_COOKIE)?.value;
  const sessionSurface = surfaceCookie === "ops" || surfaceCookie === "operator" ? surfaceCookie : null;
  const pathSurface = surfaceForPath(pathname);

  if (!hasSession) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = loginPathForSurface(pathSurface);
    loginUrl.searchParams.set("next", `${pathname}${request.nextUrl.search}`);
    return NextResponse.redirect(loginUrl);
  }

  if (sessionSurface && sessionSurface !== pathSurface) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = loginPathForSurface(pathSurface);
    loginUrl.searchParams.set("next", `${pathname}${request.nextUrl.search}`);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Exclude static fonts — otherwise /fonts/*.woff2 is redirected to login HTML and Google Sans never loads.
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|fonts/|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2|woff|ttf|otf)$).*)"
  ]
};
