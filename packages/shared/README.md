# packages/shared

Shared contracts and lightweight helpers for `reup-douyin`.

## Responsibility

- Own shared schemas, types, constants, and documentation helpers.
- Keep cross-app contracts consistent between web, API, and worker code.
- Stay dependency-light and safe to import across boundaries.

## Boundaries

- Do not place app-specific runtime orchestration here.
- Do not add infrastructure clients here unless they are pure interfaces or shared contract definitions.
- Do not hide business workflows inside generic helpers.

## Current Status

Bootstrap placeholder only. No shared schemas or constants have been implemented.

