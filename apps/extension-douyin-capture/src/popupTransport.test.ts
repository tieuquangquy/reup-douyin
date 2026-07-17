import assert from "node:assert/strict";
import {
  ExtensionDirectExecutionError,
  executeCurrentTabAction,
  isSupportedDouyinUrl,
  projectDirectExecutionError,
  type DirectExecutionRuntime,
  type DirectExecutionResult,
  type ExtensionDirectAction
} from "./popupTransport";
import type { DouyinPageType, ExtensionCapturePayload, PageSnapshot } from "./types";

assert.equal(isSupportedDouyinUrl("https://www.douyin.com/user/MS4wLjABAAAAfixture"), true);
assert.equal(isSupportedDouyinUrl("https://creator.douyin.com/creator-micro/home"), true);
assert.equal(isSupportedDouyinUrl("https://foo.iesdouyin.com/share/video/123"), true);
assert.equal(isSupportedDouyinUrl("http://www.douyin.com/user/MS4wLjABAAAAfixture"), false);
assert.equal(isSupportedDouyinUrl("https://example.com/"), false);
assert.equal(isSupportedDouyinUrl("not-a-url"), false);

{
  const runtime = createRuntime({ tab: { id: 123, url: "https://www.douyin.com/user/MS4wLjABAAAAfixture" }, result: { ok: true, page: pageFixture() } });
  const response = await executeCurrentTabAction("detect", runtime);
  assert.equal(response.ok, true);
  assert.equal(response.page?.page_type, "profile_page");
  assert.equal(runtime.calls.execute, 1);
  assert.equal(runtime.actions[0], "detect");
}

{
  const runtime = createRuntime({ tab: { id: 123, url: "https://example.com/" }, result: { ok: true, page: pageFixture() } });
  await assert.rejects(() => executeCurrentTabAction("detect", runtime), (error) => {
    assert.equal(error instanceof ExtensionDirectExecutionError, true);
    assert.equal((error as ExtensionDirectExecutionError).code, "unsupported_tab");
    assert.equal((error as Error).message, "Open a supported Douyin page and refresh it, then try again.");
    assert.equal(runtime.calls.execute, 0);
    return true;
  });
}

{
  const runtime = createRuntime({ tab: { id: 123, url: "https://www.douyin.com/passport/login" }, result: { ok: false, page: pageFixture("login_page"), error_code: "login_page" } });
  await assert.rejects(() => executeCurrentTabAction("detect", runtime), (error) => {
    assert.equal(error instanceof ExtensionDirectExecutionError, true);
    assert.equal((error as ExtensionDirectExecutionError).code, "login_page");
    assert.equal((error as Error).message, "This Douyin page is asking for login. Log in in the browser, refresh the page, and try again.");
    assert.equal(runtime.calls.execute, 1);
    return true;
  });
}

{
  const runtime = createRuntime({ tab: { id: 123, url: "https://www.douyin.com/verify" }, result: { ok: false, page: pageFixture("challenge_page"), error_code: "challenge_page" } });
  await assert.rejects(() => executeCurrentTabAction("capture", runtime), (error) => {
    assert.equal(error instanceof ExtensionDirectExecutionError, true);
    assert.equal((error as ExtensionDirectExecutionError).code, "challenge_page");
    assert.equal((error as Error).message, "Douyin is showing a challenge. Solve it in the browser, refresh the page, and try again.");
    assert.equal(runtime.calls.execute, 1);
    return true;
  });
}

{
  const payload = capturePayloadFixture();
  const runtime = createRuntime({ tab: { id: 123, url: "https://www.douyin.com/video/123" }, result: { ok: true, payload } });
  const response = await executeCurrentTabAction("capture", runtime);
  assert.equal(response.ok, true);
  assert.equal(response.payload?.schema_version, "douyin_extension_capture.v1");
  assert.equal(response.payload?.diagnostics.extractor, "direct_execute_script_dom_fallback_v1");
  assert.equal(runtime.calls.execute, 1);
  assert.equal(runtime.actions[0], "capture");
}

{
  const runtime = createRuntime({ tab: { id: 123, url: "https://www.douyin.com/video/123" }, executionError: new Error("Cannot access contents of this page") });
  await assert.rejects(() => executeCurrentTabAction("detect", runtime), (error) => {
    assert.equal(error instanceof ExtensionDirectExecutionError, true);
    assert.equal((error as ExtensionDirectExecutionError).code, "direct_execution_failed");
    assert.equal((error as Error).message, "Could not execute the Douyin detector in this tab. Reconnect Douyin Tab. If reconnect fails, reload the extension, then hard refresh the Douyin tab.");
    assert.equal(runtime.calls.execute, 1);
    return true;
  });
}

{
  const friendly = projectDirectExecutionError(new Error("Could not establish connection. Receiving end does not exist."));
  assert.equal(friendly.code, "direct_execution_failed");
  assert.equal(friendly.message, "Could not execute the Douyin detector in this tab. Reconnect Douyin Tab. If reconnect fails, reload the extension, then hard refresh the Douyin tab.");
}

console.log("extension direct execution transport tests passed");

type RuntimeOptions = {
  tab: { id?: number; url?: string } | null;
  result?: DirectExecutionResult;
  executionError?: Error;
};

function createRuntime(options: RuntimeOptions): DirectExecutionRuntime & { calls: { execute: number }; actions: ExtensionDirectAction[] } {
  const calls = { execute: 0 };
  const actions: ExtensionDirectAction[] = [];

  return {
    calls,
    actions,
    async queryActiveTab() {
      return options.tab;
    },
    async executeInTab(_tabId: number, action: ExtensionDirectAction) {
      calls.execute += 1;
      actions.push(action);
      if (options.executionError) throw options.executionError;
      if (!options.result) throw new Error("No fixture response configured");
      return options.result;
    }
  };
}

function pageFixture(pageType: DouyinPageType = "profile_page"): PageSnapshot {
  return {
    url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
    title: "Fixture creator",
    page_type: pageType,
    profile_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
    video_link_count: 3
  };
}

function capturePayloadFixture(): ExtensionCapturePayload {
  return {
    schema_version: "douyin_extension_capture.v1",
    capture_id: "capture-fixture",
    captured_at: "2026-04-26T17:24:00.000Z",
    page: pageFixture("video_detail_page"),
    profile: { id: "MS4wLjABAAAAfixture", sec_uid: "MS4wLjABAAAAfixture", handle: null, display_name: "Fixture creator" },
    capture_context: {
      capture_id: "capture-fixture",
      tab_id: null,
      page_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      page_url_normalized: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      profile_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      profile_external_id: "MS4wLjABAAAAfixture",
      captured_at: "2026-04-26T17:24:00.000Z",
      cache_scope_key: "https://www.douyin.com/user/MS4wLjABAAAAfixture|https://www.douyin.com/user/MS4wLjABAAAAfixture|MS4wLjABAAAAfixture"
    },
    videos: [],
    diagnostics: {
      extension_version: "0.1.0",
      extractor: "direct_execute_script_dom_fallback_v1",
      visible_video_count: 0,
      page_type: "video_detail_page"
    }
  };
}
