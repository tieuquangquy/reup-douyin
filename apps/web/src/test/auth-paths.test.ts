import assert from "node:assert/strict";
import { sanitizeNextPath, SESSION_PRESENCE_COOKIE } from "../lib/authPaths";
import {
  homePathForSurface,
  isOpsConsolePath,
  loginPathForSurface,
  surfaceForPath,
  authenticatedLoginBounceTarget
} from "../lib/authSurface";

assert.equal(SESSION_PRESENCE_COOKIE, "reup_douyin_session");
assert.equal(sanitizeNextPath("/capture-inbox", "/"), "/capture-inbox");
assert.equal(sanitizeNextPath("https://evil.example/phish", "/"), "/");
assert.equal(sanitizeNextPath("/auth/login", "/"), "/");
assert.equal(sanitizeNextPath("//evil.example", "/"), "/");

assert.equal(isOpsConsolePath("/ops"), true);
assert.equal(isOpsConsolePath("/ops/jobs"), true);
assert.equal(isOpsConsolePath("/ops/pipeline"), false);
assert.equal(isOpsConsolePath("/ops/extensions/douyin"), true);
assert.equal(isOpsConsolePath("/ops/extensions/douyin/capture-inbox"), false);
assert.equal(isOpsConsolePath("/selection/capture-inbox"), false);
assert.equal(isOpsConsolePath("/selection/review-board"), false);
assert.equal(surfaceForPath("/ops/caption-ai"), "ops");
assert.equal(surfaceForPath("/ops/pipeline"), "operator");
assert.equal(surfaceForPath("/publishing/accounts"), "operator");
assert.equal(surfaceForPath("/ops/extensions/douyin/capture-inbox"), "operator");
assert.equal(surfaceForPath("/selection/capture-inbox"), "operator");
assert.equal(loginPathForSurface("ops"), "/auth/ops/login");
assert.equal(loginPathForSurface("operator"), "/auth/login");
assert.equal(homePathForSurface("ops"), "/ops");
assert.equal(homePathForSurface("operator"), "/");

// Cross-surface switch: stay on the *other* surface's login while session is still active.
assert.equal(authenticatedLoginBounceTarget("/auth/ops/login", "operator"), null, "Studio session must reach Ops login to switch");
assert.equal(authenticatedLoginBounceTarget("/auth/login", "ops"), null, "Ops session must reach Studio login to switch");
assert.equal(authenticatedLoginBounceTarget("/auth/register", "ops"), null, "Ops session must reach Studio register when switching");
// Same-surface login: bounce home (already authenticated for that portal).
assert.equal(authenticatedLoginBounceTarget("/auth/ops/login", "ops"), "/ops");
assert.equal(authenticatedLoginBounceTarget("/auth/login", "operator"), "/");
assert.equal(authenticatedLoginBounceTarget("/auth/register", "operator"), "/");
assert.equal(authenticatedLoginBounceTarget("/selection/review-board", "operator"), null);

console.log("auth-paths + auth-surface tests passed");
