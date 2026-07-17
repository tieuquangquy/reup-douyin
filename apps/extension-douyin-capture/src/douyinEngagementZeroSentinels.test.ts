import assert from "node:assert/strict";
import { parseDouyinEngagementCount, parseDouyinEngagementText } from "./douyinEngagementZeroSentinels";

assert.equal(parseDouyinEngagementText("comment", "抢首评").kind, "zero_sentinel");
assert.equal(parseDouyinEngagementText("comment", "抢首评").value, 0);
assert.equal(parseDouyinEngagementText("comment", "快来抢首评").kind, "zero_sentinel");
assert.equal(parseDouyinEngagementText("comment", "评论 128").kind, "missing");
assert.equal(parseDouyinEngagementText("share", "分享", { shareIconContext: true }).kind, "zero_sentinel");
assert.equal(parseDouyinEngagementText("share", "分享", { shareIconContext: false }).kind, "missing");
assert.equal(parseDouyinEngagementText("share", "分享 12", { shareIconContext: true }).kind, "missing");
assert.equal(parseDouyinEngagementCount("comment", "抢首评"), 0);
assert.equal(parseDouyinEngagementCount("share", "分享", { shareIconContext: true }), 0);
assert.equal(parseDouyinEngagementCount("share", "分享"), null);

console.log("douyinEngagementZeroSentinels.test.ts passed");
