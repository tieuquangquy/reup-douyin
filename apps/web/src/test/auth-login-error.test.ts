/**
 * Auth login error copy — humanize bare HTTP status dumps for the banner.
 */
import assert from "node:assert/strict";
import { resolveAuthLoginError } from "../lib/authLoginError";

const copy = {
  title: "Couldn't sign in",
  serverUnavailable:
    "The sign-in service is temporarily unavailable. Confirm the API is running, then try again.",
  unauthorized: "Email, password, or workspace slug doesn't match. Check and try again.",
  forbidden: "This account can't access this console.",
  network: "Couldn't reach the server. Check your connection and that the API is up.",
  generic: "Something went wrong while signing in. Please try again."
};

{
  const view = resolveAuthLoginError("Login failed: 500", copy);
  assert.equal(view.title, copy.title);
  assert.equal(view.message, copy.serverUnavailable);
  assert.doesNotMatch(view.message, /\b500\b/, "server errors must not dump bare status codes");
}

{
  const view = resolveAuthLoginError("Login failed: 401: Invalid credentials", copy);
  assert.equal(view.message, "Invalid credentials");
}

{
  const view = resolveAuthLoginError("Login failed: 403", copy);
  assert.equal(view.message, copy.forbidden);
}

{
  const view = resolveAuthLoginError("Failed to fetch", copy);
  assert.equal(view.message, copy.network);
}

{
  const view = resolveAuthLoginError("", copy);
  assert.equal(view.message, copy.generic);
}

console.log("auth-login-error tests passed");
