import assert from "node:assert/strict";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, extname, join, relative, sep } from "node:path";
import { execFileSync } from "node:child_process";

const root = process.cwd();
const distDir = join(root, "dist");
const releaseRoot = join(root, "release");
const packageDir = join(releaseRoot, "reup-douyin-extension-0.1.0");
const packageZip = join(releaseRoot, "reup-douyin-extension-0.1.0.zip");
const reportPath = join(releaseRoot, "package-hygiene-report.json");

const excludedFilePatterns = [
  "node_modules",
  "*.test.js",
  "*.test.ts",
  "*.map",
  ".env*",
  "*.log",
  "coverage",
  "screenshots",
  "tmp",
  "temp",
  "docs"
];

const forbiddenFilePredicates = [
  (path) => path.split(sep).includes("node_modules"),
  (path) => path.split(sep).includes("coverage"),
  (path) => path.split(sep).includes("screenshots"),
  (path) => path.split(sep).includes("tmp"),
  (path) => path.split(sep).includes("temp"),
  (path) => path.split(sep).includes("docs"),
  (path) => basename(path).startsWith(".env"),
  (path) => basename(path).endsWith(".log"),
  (path) => basename(path).endsWith(".map"),
  (path) => basename(path).endsWith(".test.js"),
  (path) => basename(path).endsWith(".test.ts")
];

const suspiciousValuePatterns = [
  { name: "assignment_cookie", pattern: /(?:cookie|authorization|auth[_-]?token|csrf|password|api[_-]?key|secret)\s*[:=]\s*["'][^"']{8,}["']/i },
  { name: "bearer_token", pattern: /Bearer\s+[A-Za-z0-9._~+/=-]{16,}/i },
  { name: "private_key", pattern: /-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----/i },
  { name: "raw_local_path", pattern: /C:\\Users\\[^"'\s]+/i }
];

function walkFiles(dir) {
  if (!existsSync(dir)) return [];
  const entries = readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? walkFiles(path) : [path];
  });
}

function copyDir(source, destination) {
  mkdirSync(destination, { recursive: true });
  for (const entry of readdirSync(source, { withFileTypes: true })) {
    const sourcePath = join(source, entry.name);
    const destinationPath = join(destination, entry.name);
    if (entry.isDirectory()) {
      copyDir(sourcePath, destinationPath);
    } else {
      copyFileSync(sourcePath, destinationPath);
    }
  }
}

function toPosix(path) {
  return path.split(sep).join("/");
}

function shouldExclude(path) {
  return forbiddenFilePredicates.some((predicate) => predicate(path));
}

assert.equal(existsSync(distDir), true, "dist must exist before packaging");
assert.equal(existsSync(join(distDir, "manifest.json")), true, "manifest.json must exist in dist");

rmSync(releaseRoot, { recursive: true, force: true });
mkdirSync(releaseRoot, { recursive: true });
copyDir(distDir, packageDir);

const copiedFiles = walkFiles(packageDir);
const excludedFiles = copiedFiles.filter(shouldExclude).map((path) => toPosix(relative(packageDir, path)));
for (const excluded of excludedFiles) {
  rmSync(join(packageDir, excluded), { force: true });
}

const packageFiles = walkFiles(packageDir);
const forbiddenFileMatches = packageFiles.filter(shouldExclude).map((path) => toPosix(relative(packageDir, path)));
const forbiddenPatternMatches = [];
for (const file of packageFiles) {
  const extension = extname(file).toLowerCase();
  if (![".js", ".json", ".html", ".css"].includes(extension)) continue;
  const content = readFileSync(file, "utf-8");
  for (const { name, pattern } of suspiciousValuePatterns) {
    if (pattern.test(content)) {
      forbiddenPatternMatches.push({ file: toPosix(relative(packageDir, file)), pattern: name });
    }
  }
}

const manifest = JSON.parse(readFileSync(join(packageDir, "manifest.json"), "utf-8"));
assert.equal(manifest.manifest_version, 3, "release package must include an MV3 manifest");
assert.equal(manifest.version, "0.1.0", "release package version must match expected release version");
assert.equal(existsSync(join(packageDir, "popup.html")), true, "release package must include popup.html");
assert.equal(existsSync(join(packageDir, "popup.js")), true, "release package must include popup.js");
assert.equal(existsSync(join(packageDir, "background.js")), true, "release package must include background.js");
assert.equal(existsSync(join(packageDir, "contentScript.js")), true, "release package must include contentScript.js");

const packageHygienePassed = forbiddenFileMatches.length === 0 && forbiddenPatternMatches.length === 0;
const report = {
  release_status: packageHygienePassed ? "ready_for_operator_trial" : "blocked",
  package_hygiene_passed: packageHygienePassed,
  package_output_path: toPosix(relative(root, packageDir)),
  package_zip_path: toPosix(relative(root, packageZip)),
  package_file_count: packageFiles.length,
  package_size_bytes: packageFiles.reduce((total, file) => total + statSync(file).size, 0),
  package_excluded_files: excludedFiles.sort(),
  package_excluded_file_patterns: excludedFilePatterns,
  forbidden_file_matches: forbiddenFileMatches.sort(),
  forbidden_pattern_matches: forbiddenPatternMatches,
  checked_at: new Date().toISOString()
};

writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf-8");

if (!packageHygienePassed) {
  console.error(JSON.stringify(report, null, 2));
  process.exit(1);
}

rmSync(packageZip, { force: true });
execFileSync("powershell", [
  "-NoProfile",
  "-ExecutionPolicy",
  "Bypass",
  "-Command",
  `Compress-Archive -Path '${packageDir.replaceAll("'", "''")}\\*' -DestinationPath '${packageZip.replaceAll("'", "''")}' -Force`
], { stdio: "inherit" });

console.log(JSON.stringify(report, null, 2));
