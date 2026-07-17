import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  buildCaptureInboxWebUrl,
  CAPTURE_INBOX_WEB_ROUTE,
  DEFAULT_WEB_APP_ORIGIN,
  normalizeWebAppOrigin
} from "./captureInboxNavigation.js";

assert.equal(normalizeWebAppOrigin("http://localhost:3000/"), "http://localhost:3000");
assert.equal(normalizeWebAppOrigin(""), DEFAULT_WEB_APP_ORIGIN);
assert.equal(normalizeWebAppOrigin(null), DEFAULT_WEB_APP_ORIGIN);
assert.equal(
  buildCaptureInboxWebUrl("http://127.0.0.1:3000"),
  `http://127.0.0.1:3000${CAPTURE_INBOX_WEB_ROUTE}`
);
assert.equal(
  buildCaptureInboxWebUrl("http://127.0.0.1:3000", "https://www.douyin.com/user/MS4wLjABAAAAtest"),
  `http://127.0.0.1:3000${CAPTURE_INBOX_WEB_ROUTE}?profile_url=${encodeURIComponent("https://www.douyin.com/user/MS4wLjABAAAAtest")}`
);

const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");
assert.match(popupSource, /from "\.\/captureInboxNavigation\.js"/, "popup must import capture inbox navigation helpers");
assert.match(popupSource, /case "open_capture_inbox":[\s\S]*openCaptureInboxWebAppFromPopup\(\)/, "open_capture_inbox primary action must open the web Capture Inbox");
assert.match(popupSource, /openCaptureInboxWebTab\(webAppOrigin, profileUrl\)/, "open_capture_inbox must pass active harvest profile_url into the web deep link");
assert.match(popupSource, /scannerOpenCaptureInboxButton\?\.addEventListener\("click", \(\) => void openCaptureInboxWebAppFromPopup\(\)\)/, "footer Capture Inbox action must open the web Capture Inbox");
assert.match(popupSource, /openResultsDashboardButton\?\.addEventListener\("click", \(\) => void setDeckActivePanel\("results"\)\)/, "advanced Results Dashboard action must keep legacy results panel access");

const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
assert.match(popupHtml, /id="webAppOrigin"/, "popup must expose configurable web app origin");
assert.match(popupHtml, /id="openResultsDashboardButton"/, "popup must expose legacy Results Dashboard entry in Advanced");

console.log("captureInboxNavigation.test.ts passed");
