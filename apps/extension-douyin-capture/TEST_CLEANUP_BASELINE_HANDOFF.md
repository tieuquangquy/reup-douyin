# Test Cleanup Baseline Handoff

## Scope

This handoff freezes the validated baseline for the conservative extension test cleanup track in `apps/extension-douyin-capture`.

Included scope:

- assertion-diagnostic guardrails for `src/wholeProfileHarvest.test.ts`
- staged local rollout commands at the repository root
- repository-level workflow documentation updates
- validation of extension test/build behavior after the guardrail rollout

Excluded scope:

- runtime/controller production code changes
- semantic test rewrites beyond the previously completed conservative cleanup work
- new CI workflow creation from scratch
- broad duplicate-assertion refactors outside the validated baseline

## Changes Completed

1. Added staged root scripts in `package.json`:
   - `npm run extension:test:guardrails` -> soft mode
   - `npm run extension:test:guardrails:warn`
   - `npm run extension:test:guardrails:strict`
2. Extended `scripts/check-extension-test-assertions.mjs` to support `--mode=warn|soft|strict`.
3. Documented the rollout in `README.md` under `## Extension Test Guardrails`.
4. Kept rollout script-first because this workspace currently has no existing `.github/workflows` entry point to extend conservatively.

## Validation Baseline

Confirmed baseline for this cleanup track:

- `npm run extension:test` -> passed
- `npm run extension:build` -> passed
- `npm run extension:test:guardrails:warn` -> passed with exit code 0 and non-blocking findings
- `npm run extension:test:guardrails` -> configured as soft mode for day-to-day rollout
- `npm run extension:test:guardrails:strict` -> failed as designed because one duplicate assertion warning remains

Known current strict finding:

- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:3719` duplicates `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1345`

## Safety Boundaries

- This baseline is test-only and workflow-only.
- No runtime behavior or production code paths were changed for this phase.
- No new heavy dependencies were introduced.
- The default rollout remains non-disruptive by keeping the root guardrail command in soft mode.
- CI was intentionally not introduced because no existing repository workflow entry point was available to extend conservatively.

## Known Limitations / Deferred Work

- Strict mode is not yet suitable as the default blocking gate because one duplicate assertion warning remains.
- No git-based branch/worktree diff could be captured in this environment because the workspace is not mounted as a git repository.
- The guardrail currently targets the highest-risk assertion regions in `wholeProfileHarvest.test.ts`; it is not yet a generalized repository-wide assertion policy.
- No new `.github/workflows` file was added in this phase.

## Recommended Next Step

Perform one focused follow-up cleanup pass on the remaining duplicate assertion in `wholeProfileHarvest.test.ts`, re-run strict mode, and only then consider promoting `extension:test:guardrails:strict` into an existing CI workflow when the repository has a natural workflow entry point.
