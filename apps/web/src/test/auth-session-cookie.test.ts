/**
 * Soft HTML session cookies must outlive browser restarts while refresh tokens remain valid.
 * Otherwise middleware redirects / → /auth/login and AuthProvider flashes LoginPage before home.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { SESSION_PRESENCE_COOKIE, SESSION_SOFT_COOKIE_MAX_AGE_SECONDS } from "../lib/authPaths";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const apiSource = readFileSync(resolve(webSrc, "lib/api.ts"), "utf8");
const authSource = readFileSync(resolve(webSrc, "lib/auth.tsx"), "utf8");
const pathsSource = readFileSync(resolve(webSrc, "lib/authPaths.ts"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.equal(SESSION_PRESENCE_COOKIE, "reup_douyin_session");
assert.equal(
  SESSION_SOFT_COOKIE_MAX_AGE_SECONDS,
  14 * 24 * 60 * 60,
  "Soft session cookie Max-Age must align with default refresh TTL (14 days)"
);
assert.match(pathsSource, /SESSION_SOFT_COOKIE_MAX_AGE_SECONDS/, "authPaths must export soft cookie Max-Age");
assert.match(
  apiSource,
  /Max-Age=\$\{SESSION_SOFT_COOKIE_MAX_AGE_SECONDS\}/,
  "Presence and surface soft cookies must set durable Max-Age (not browser-session cookies)"
);
assert.match(
  apiSource,
  /setSessionPresenceCookie\(true\);\s*const surface = getAuthSurface\(\);\s*if \(surface\) setSessionSurfaceCookie\(surface\);/,
  "Restoring an access token must refresh the surface soft cookie when surface is known"
);
assert.match(
  authSource,
  /const loginBounce = authenticatedLoginBounceTarget\([\s\S]*?if \(loginBounce\) \{\s*return <AuthBootScreen/,
  "AuthProvider must suppress LoginPage paint while bouncing an authenticated session off login"
);
assert.match(pkg, /auth-session-cookie\.test\.ts/, "package.json must run auth-session-cookie test");

console.log("auth-session-cookie tests passed");
