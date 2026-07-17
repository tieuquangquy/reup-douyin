import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const generatedDir = join(root, "src", "generated");
const timestamp = new Date().toISOString();
const buildId = `reup-douyin-extension-${timestamp.replace(/[:.]/g, "-")}`;

mkdirSync(generatedDir, { recursive: true });
writeFileSync(
  join(generatedDir, "buildIdentity.ts"),
  `export const EXTENSION_BUILD_TIMESTAMP = ${JSON.stringify(timestamp)};\nexport const EXTENSION_RUNTIME_BUILD_ID = ${JSON.stringify(buildId)};\nexport const BACKGROUND_RUNTIME_BUILD_ID = EXTENSION_RUNTIME_BUILD_ID;\nexport const POPUP_RUNTIME_BUILD_ID = EXTENSION_RUNTIME_BUILD_ID;\nexport const CONTENT_SCRIPT_RUNTIME_BUILD_ID = EXTENSION_RUNTIME_BUILD_ID;\n`,
  "utf8"
);

console.log(`[reup-douyin-extension] generated build identity ${buildId}`);
