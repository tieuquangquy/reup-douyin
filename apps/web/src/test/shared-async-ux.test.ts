import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createAsyncActionGate } from "../lib/useAsyncAction";
import { createLatestRequestController } from "../lib/useLatestRequest";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");
const asyncButtonSource = readFileSync(resolve(webRoot, "components/shared/AsyncButton.tsx"), "utf8");
const asyncActionSource = readFileSync(resolve(webRoot, "lib/useAsyncAction.ts"), "utf8");
const latestRequestSource = readFileSync(resolve(webRoot, "lib/useLatestRequest.ts"), "utf8");

let invocationCount = 0;
let releaseAction!: () => void;
const gate = createAsyncActionGate();
const first = gate.run("save", () => {
  invocationCount += 1;
  return new Promise<void>((resolve) => {
    releaseAction = resolve;
  });
});
const duplicate = gate.run("save", () => {
  invocationCount += 1;
  return Promise.resolve();
});
assert.equal(invocationCount, 1, "Same-frame duplicate actions must invoke the mutation once");
assert.equal(first, duplicate, "Dropped duplicate actions must share the in-flight promise");
releaseAction();
await first;
assert.equal(gate.isPending("save"), false, "Action gate must release its key after settlement");

const requests = createLatestRequestController();
const older = requests.start();
const newer = requests.start();
assert.equal(older.signal.aborted, true, "Starting a newer request must abort the older request");
assert.equal(older.isLatest(), false, "Older responses must not be allowed to commit");
assert.equal(newer.isLatest(), true, "Newest response must remain authoritative");
requests.cancel();
assert.equal(newer.signal.aborted, true, "Explicit cancellation must abort the current request");

assert.match(asyncButtonSource, /aria-busy=\{pending \|\| undefined\}/, "AsyncButton must expose pending state");
assert.match(asyncButtonSource, /disabled=\{disabled \|\| pending\}/, "AsyncButton must prevent repeated clicks while pending");
assert.match(asyncButtonSource, /async-button__spinner/, "AsyncButton must render a stable pending spinner");
assert.match(asyncButtonSource, /const showIcon = pending \|\| leadingIcon != null;/, "AsyncButton must not reserve an empty leading-icon slot");
assert.match(asyncButtonSource, /\{showIcon \? \(/, "AsyncButton icon slot must render only when it has visible content");
assert.match(
  readFileSync(resolve(webRoot, "app/globals.css"), "utf8"),
  /\.async-button__label\s*\{[^}]*align-items: center;[^}]*display: inline-flex;[^}]*gap: 0\.4rem;/,
  "AsyncButton labels must align composite icon and text children on one row"
);
assert.match(asyncActionSource, /mountedRef/, "useAsyncAction must suppress state commits after unmount");
assert.match(latestRequestSource, /AbortController/, "useLatestRequest must cancel superseded reads");

console.log("shared async UX tests passed");
