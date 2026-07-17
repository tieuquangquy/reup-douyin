import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createPageMetadata, pageMetadata, rootMetadata, SITE_NAME } from "../lib/pageMetadata";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");
const layoutSource = readFileSync(resolve(webRoot, "app/layout.tsx"), "utf8");
const reviewBoardPageSource = readFileSync(resolve(webRoot, "app/selection/review-board/page.tsx"), "utf8");
const reupQueuePageSource = readFileSync(resolve(webRoot, "app/selection/reup-queue/page.tsx"), "utf8");
const exportPackagePageSource = readFileSync(resolve(webRoot, "app/publishing/export-packages/[packageId]/page.tsx"), "utf8");
const loginLayoutSource = readFileSync(resolve(webRoot, "app/auth/login/layout.tsx"), "utf8");

assert.equal(SITE_NAME, "Reup Douyin");
assert.deepEqual(rootMetadata.title, { default: SITE_NAME, template: `%s | ${SITE_NAME}` });
assert.equal(createPageMetadata({ title: "Review Board", description: "Test" }).title, "Review Board");
assert.equal(pageMetadata.reviewBoard.title, "Review Board");
assert.equal(pageMetadata.reupQueue.title, "Reup Queue");

assert.match(layoutSource, /rootMetadata/, "Root layout must use shared root metadata");
assert.doesNotMatch(layoutSource, /title:\s*"reup-douyin"/, "Root layout must not keep the old static title");
assert.match(reviewBoardPageSource, /pageMetadata\.reviewBoard/, "Review Board route must export page metadata");
assert.match(reupQueuePageSource, /pageMetadata\.reupQueue/, "Reup Queue route must export page metadata");
assert.match(exportPackagePageSource, /generateMetadata/, "Export package detail route must generate metadata");
assert.match(loginLayoutSource, /pageMetadata\.signIn/, "Login route layout must export sign-in metadata");

console.log("page-metadata tests passed");
