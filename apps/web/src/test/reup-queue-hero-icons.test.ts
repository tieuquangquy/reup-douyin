/**
 * The three queue-start CTAs run different pipelines, so each needs its own glyph.
 * Sharing kind="process" made "Start auto", "Auto→Render" and "Start manual" look identical.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const iconSource = readFileSync(resolve(webSrc, "components/shared/WorkItemActionIcon.tsx"), "utf8");
const reupSource = readFileSync(resolve(webSrc, "components/reup-queue/ReupQueuePage.tsx"), "utf8");

for (const kind of ["auto-run", "auto-render", "step"]) {
  assert.match(
    iconSource,
    new RegExp(`"${kind}"`),
    `WorkItemActionIcon must declare the ${kind} glyph`
  );
}

const heroRail = reupSource.slice(
  reupSource.indexOf("reup-queue-hero-action-rail"),
  reupSource.indexOf("ariaLabel=\"Reup Queue quick path\"")
);
assert.ok(heroRail.length > 0, "Hero action rail block must be locatable");

const heroKinds = [...heroRail.matchAll(/kind="([a-z-]+)"/g)].map((match) => match[1]);
assert.equal(heroKinds.length, 4, "Hero rail must render four action icons");
assert.equal(
  new Set(heroKinds).size,
  heroKinds.length,
  `Every hero CTA must use a distinct glyph, got ${heroKinds.join(", ")}`
);
assert.deepEqual(
  heroKinds,
  ["auto-render", "auto-run", "step", "open"],
  "Hero rail order must be full auto through render, auto stopping at TTS, single manual step, open board"
);

console.log("reup-queue-hero-icons tests passed");
