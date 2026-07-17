import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  backendHttpError,
  backendTimeoutError,
  createPopupActionState,
  projectPopupActionError,
  runPopupAction,
  withTimeout,
  type PopupFriendlyError
} from "./popupActions";
import { ExtensionDirectExecutionError } from "./popupTransport";

const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf-8");
const popupProgressSource = readFileSync(new URL("./popupProgress.ts", import.meta.url), "utf-8");
const popupWorkflowSource = readFileSync(new URL("./popupWorkflow.ts", import.meta.url), "utf-8");

const capturedErrors: PopupFriendlyError[] = [];

{
  const state = createPopupActionState();
  const events: string[] = [];
  capturedErrors.length = 0;

  await runPopupAction(
    "check_connection",
    {
      setLoading(loading) {
        events.push(loading ? "loading" : "idle");
      },
      renderError(error) {
        capturedErrors.push(error);
      }
    },
    async () => {
      throw backendTimeoutError();
    },
    state
  );

  assert.deepEqual(events, ["loading", "idle"]);
  assert.equal(state.loading, false);
  assert.equal(state.lastAction, "check_connection");
  assert.equal(state.lastErrorCategory, "backend_timeout");
  assert.equal(capturedErrors[0]?.category, "backend_timeout");
}

{
  const state = createPopupActionState();
  let runs = 0;
  await runPopupAction(
    "detect_current_page",
    noopRenderer(),
    async () => {
      runs += 1;
      throw new ExtensionDirectExecutionError("no_active_tab", "No active tab is available. Open a supported Douyin tab and try again.");
    },
    state
  );
  assert.equal(runs, 1);
  assert.equal(state.loading, false);
  assert.equal(state.lastErrorCategory, "no_active_tab");

  await runPopupAction(
    "capture_current_page",
    noopRenderer(),
    async () => {
      runs += 1;
    },
    state
  );
  assert.equal(runs, 2);
  assert.equal(state.loading, false);
  assert.equal(state.lastAction, "capture_current_page");
  assert.equal(state.lastErrorCategory, null);
}

{
  const unsupported = projectPopupActionError(
    new ExtensionDirectExecutionError("unsupported_tab", "Open a supported Douyin page and refresh it, then try again."),
    "detect_current_page"
  );
  assert.equal(unsupported.category, "unsupported_tab");

  const challenge = projectPopupActionError(
    new ExtensionDirectExecutionError("challenge_page", "Douyin is showing a challenge. Solve it in the browser, refresh the page, and try again."),
    "capture_current_page"
  );
  assert.equal(challenge.category, "challenge_page");

  const capture = projectPopupActionError(new Error("Backend rejected capture payload."), "capture_current_page");
  assert.equal(capture.category, "capture_failed");
  assert.equal(capture.message, "Backend rejected capture payload.");
}

{
  const backend = projectPopupActionError(
    backendHttpError("Backend validation failed (code: extension_capture_validation_error, stage: request_validation_failed, diagnostics: diag-fixture)"),
    "capture_current_page"
  );
  assert.equal(backend.category, "backend_error");
  assert.match(backend.message, /code: extension_capture_validation_error/);
  assert.match(backend.message, /stage: request_validation_failed/);
  assert.match(backend.message, /diagnostics: diag-fixture/);
}

{
  const backend = projectPopupActionError(
    backendHttpError("Capture Inbox database schema is missing required tables. Apply migrations and restart the backend on the extension API port. (code: schema_missing, stage: capture_inbox_schema_readiness, diagnostics: diag-schema-fixture)"),
    "capture_current_page"
  );
  assert.equal(backend.category, "backend_error");
  assert.match(backend.message, /code: schema_missing/);
  assert.match(backend.message, /stage: capture_inbox_schema_readiness/);
  assert.match(backend.message, /diagnostics: diag-schema-fixture/);
}

assert.match(popupSource, /formatBackendError/, "popup must format structured backend errors");
assert.match(popupSource, /detail\.code/, "popup backend errors must include backend error code when provided");
assert.match(popupSource, /detail\.stage/, "popup backend errors must include backend stage when provided");
assert.match(popupSource, /detail\.diagnostics_id/, "popup backend errors must include backend diagnostics id when provided");
assert.match(popupSource, /buildModalWholeProfileHarvestPlanPayload/, "modal dev tools must still build harvest-plan payloads for capture summaries");
assert.match(popupSource, /REUP_DOUYIN_PROBE_CURRENT_MODAL/, "popup must expose a probe action before full harvest");
assert.doesNotMatch(popupSource, /async function runSmartCaptureHarvest/, "legacy Smart Capture orchestration must be removed from popup");
assert.match(popupSource, /renderHarvestProgressPanel/, "popup must still render legacy modal harvest progress panel when needed");
assert.match(popupProgressSource, /Target index/, "popup harvest progress must show target index");
assert.match(popupProgressSource, /ETA seconds/, "popup harvest progress must show ETA");
assert.match(popupWorkflowSource, /Calibrate 4 Points on the modal video\./, "popup must block harvest when calibration is missing");
assert.match(popupWorkflowSource, /Test Current Video has not passed\. Click Test Current Video first\./, "popup must block harvest when probe has not passed");
assert.match(popupSource, /staleViewportBanner[\s\S]*VIEWPORT_RECALIBRATION_MESSAGE/, "popup must clear stale viewport warning banner once the current viewport guard passes");
assert.doesNotMatch(popupSource, /Harvested modal metadata flushed to the backend\./, "legacy modal flush success copy must be removed with dead flush action");
assert.doesNotMatch(popupSource, /viewport_changed_significantly[\s\S]*backend_error/, "backend 422 handling must remain separate from stale viewport warning state");

{
  await assert.rejects(
    () => withTimeout(new Promise(() => undefined), 5, () => new Error("timed out fixture")),
    /timed out fixture/
  );
}

console.log("popup action hardening tests passed");

function noopRenderer() {
  return {
    setLoading() {
      // Test renderer intentionally does nothing.
    },
    renderError() {
      // Test renderer intentionally does nothing.
    }
  };
}
