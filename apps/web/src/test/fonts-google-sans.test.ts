import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "../..");
const fontDir = resolve(webRoot, "public/fonts/google-sans");
const srcFontDir = resolve(webRoot, "fonts/google-sans-src");
const globalCss = readFileSync(resolve(webRoot, "src/app/globals.css"), "utf8");
const layoutSource = readFileSync(resolve(webRoot, "src/app/layout.tsx"), "utf8");
const middlewareSource = readFileSync(resolve(webRoot, "src/middleware.ts"), "utf8");

/** Full Google Sans woff2 (not Latin/Viet subset) is ~450KB; subset was ~30KB. */
const MIN_FULL_WOFF2_BYTES = 300 * 1024;
const REQUIRED_WOFF2 = [
  "GoogleSans-Regular.woff2",
  "GoogleSans-Medium.woff2",
  "GoogleSans-Bold.woff2"
] as const;
const REQUIRED_SRC_TTF = [
  "GoogleSans-Regular.ttf",
  "GoogleSans-Medium.ttf",
  "GoogleSans-Bold.ttf"
] as const;

assert.ok(existsSync(fontDir), "google-sans font directory must exist");
assert.ok(existsSync(srcFontDir), "google-sans-src must exist for rebuilds");

for (const name of REQUIRED_WOFF2) {
  const path = resolve(fontDir, name);
  assert.ok(existsSync(path), `${name} must exist for runtime`);
  const size = statSync(path).size;
  assert.ok(
    size >= MIN_FULL_WOFF2_BYTES,
    `${name} must be the full Google Sans face (>=300KB), not a subset (got ${size} bytes)`
  );
}

for (const name of REQUIRED_SRC_TTF) {
  assert.ok(existsSync(resolve(srcFontDir, name)), `${name} must exist in google-sans-src`);
}

const publicFiles = readdirSync(fontDir);
assert.equal(
  publicFiles.filter((name) => name.endsWith(".ttf")).length,
  0,
  "public/fonts/google-sans must not ship .ttf (sources live in fonts/google-sans-src)"
);

assert.doesNotMatch(
  globalCss,
  /url\(["']?\/fonts\/google-sans\/[^"')]+\.ttf/,
  "@font-face must not reference .ttf fallbacks"
);
assert.doesNotMatch(
  globalCss,
  /unicode-range\s*:/,
  "full Google Sans @font-face must not restrict unicode-range"
);
assert.match(globalCss, /font-family:\s*"Google Sans"/, "must declare Google Sans @font-face");
const fontFaceBlocks = [...globalCss.matchAll(/@font-face\s*\{[^}]+\}/g)].map((match) => match[0]);
assert.ok(fontFaceBlocks.length >= 3, "must declare Regular/Medium/Bold @font-face blocks");
for (const block of fontFaceBlocks) {
  assert.doesNotMatch(
    block,
    /local\(/,
    "@font-face must not use local() Google Sans installs that can hijack self-hosted faces"
  );
}
assert.match(
  globalCss,
  /url\("\/fonts\/google-sans\/GoogleSans-Regular\.woff2"\)\s*format\("woff2"\)\s*;/,
  "Regular @font-face must use only the self-hosted woff2"
);

const preloadHrefs = [...layoutSource.matchAll(/href="(\/fonts\/google-sans\/[^"]+)"/g)].map(
  (match) => match[1]
);
assert.deepEqual(
  preloadHrefs,
  ["/fonts/google-sans/GoogleSans-Regular.woff2"],
  "critical path must preload only Regular (Medium/Bold load on demand)"
);

const nextConfigSource = readFileSync(resolve(webRoot, "next.config.mjs"), "utf8");
assert.match(nextConfigSource, /source:\s*["']\/fonts\/:path\*["']/, "must set cache headers for /fonts/*");
assert.match(
  nextConfigSource,
  /max-age=31536000.*immutable|immutable.*max-age=31536000/,
  "font cache must be long-lived immutable"
);

assert.match(
  middlewareSource,
  /matcher:\s*\[[^\]]*woff2[^\]]*\]/,
  "auth middleware matcher must exclude woff2 so /fonts/* is never redirected to login HTML"
);
assert.match(
  middlewareSource,
  /fonts\/|\\\/fonts/,
  "auth middleware matcher should also exclude the /fonts/ path prefix"
);

const replayJunk = [
  resolve(webRoot, "scripts/_globals_replay_current.css"),
  resolve(webRoot, "scripts/_globals_replay_kAX5.css")
];
for (const junk of replayJunk) {
  assert.equal(existsSync(junk), false, `unused replay CSS must be removed: ${junk}`);
}

console.log("fonts-google-sans contract tests passed");
