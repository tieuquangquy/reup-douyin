import assert from "node:assert/strict";
import {
  classifyFlagTone,
  flagsForFocusQuietSummary,
  isPipelineFlag,
  isTtsFitDuplicateFlag,
  partitionSegmentFlags,
  resolveSegmentCompareState,
  textsEqualForCompare
} from "../lib/transcriptEditorPresentation";

assert.equal(isPipelineFlag("funasr"), true);
assert.equal(isPipelineFlag("funasr_untimed"), true);
assert.equal(isPipelineFlag("duration_fit"), true);
assert.equal(isPipelineFlag("workspace_translation_prompt"), true);
assert.equal(isPipelineFlag("duration_rewrite_applied"), true);
assert.equal(isPipelineFlag("too_long"), false);
assert.equal(isPipelineFlag("caption_asr_conflict"), false);

assert.equal(classifyFlagTone("too_long"), "danger");
assert.equal(classifyFlagTone("caption_asr_conflict"), "danger");
assert.equal(classifyFlagTone("needs_operator_review"), "warn");

assert.equal(isTtsFitDuplicateFlag("too_long"), true);
assert.equal(isTtsFitDuplicateFlag("translation_too_long_for_slot"), true);
assert.equal(isTtsFitDuplicateFlag("slightly_long"), true);
assert.equal(isTtsFitDuplicateFlag("too_short"), true);
assert.equal(isTtsFitDuplicateFlag("low_confidence_source"), false);
assert.equal(isTtsFitDuplicateFlag("caption_asr_conflict"), false);

{
  // When TTS fit banner owns the length signal, quiet summary must not re-list fit/length flags.
  const quiet = flagsForFocusQuietSummary(
    [
      "too_long",
      "translation_too_long_for_slot",
      "low_confidence_source",
      "caption_asr_conflict",
      "needs_operator_review"
    ],
    "slightly_long"
  );
  assert.ok(!quiet.includes("too_long"));
  assert.ok(!quiet.includes("translation_too_long_for_slot"));
  assert.ok(quiet.includes("low_confidence_source"));
  assert.ok(quiet.includes("caption_asr_conflict"));
}

{
  // No fit problem banner → leave flags intact for the normal quiet partition.
  const untouched = flagsForFocusQuietSummary(["too_long", "low_confidence_source"], "fits_well");
  assert.ok(untouched.includes("too_long"));
  assert.ok(untouched.includes("low_confidence_source"));
}

{
  // Operator default: hide pipeline + length noise; only source-quality signal may surface.
  const partitioned = partitionSegmentFlags(
    [
      "funasr",
      "funasr_untimed",
      "duration_fit",
      "workspace_translation_prompt",
      "duration_rewrite_applied",
      "caption_asr_conflict",
      "too_long",
      "needs_operator_review",
      "low_confidence_source"
    ],
    3
  );
  assert.deepEqual(partitioned.visible, ["low_confidence_source"]);
  assert.equal(partitioned.overflowCount, 0);
  assert.equal(partitioned.pipeline.length, 0);
  assert.ok(!partitioned.visible.includes("too_long"));
  assert.ok(!partitioned.visible.includes("funasr"));
  assert.ok(!partitioned.visible.includes("caption_asr_conflict"));
}

{
  const debug = partitionSegmentFlags(
    ["funasr", "too_long", "low_confidence_source", "caption_asr_conflict"],
    3,
    { operatorQuiet: false }
  );
  assert.ok(debug.pipeline.includes("funasr"));
  assert.ok(debug.visible.includes("too_long") || debug.visible.includes("caption_asr_conflict"));
}

assert.equal(textsEqualForCompare("  Xin chao  ", "Xin chao"), true);
assert.equal(textsEqualForCompare("A", "B"), false);

{
  const unchanged = resolveSegmentCompareState({
    originalTranslatedText: "Ban dich OK",
    translatedText: "Ban dich OK",
    originalSourceText: "中文",
    sourceText: "中文",
    originalStartMs: 0,
    originalEndMs: 42000,
    startMs: 0,
    endMs: 42000
  });
  assert.equal(unchanged.vietnameseUnchanged, true);
  assert.equal(unchanged.sourceUnchanged, true);
  assert.equal(unchanged.timingUnchanged, true);
}

{
  const changed = resolveSegmentCompareState({
    originalTranslatedText: "Cu",
    translatedText: "Moi",
    originalSourceText: "中文",
    sourceText: "中文改",
    originalStartMs: 0,
    originalEndMs: 1000,
    startMs: 0,
    endMs: 2000
  });
  assert.equal(changed.vietnameseUnchanged, false);
  assert.equal(changed.sourceUnchanged, false);
  assert.equal(changed.timingUnchanged, false);
}

console.log("transcript-editor presentation tests passed");
