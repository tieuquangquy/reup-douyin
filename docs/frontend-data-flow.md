# Frontend Data Flow

The web app uses a light React state model for Phase 1. There is no global store yet.

## Review Board Data Flow

```text
ReviewBoardPage
  -> fetch /candidates
  -> fetch /filter-presets
  -> optionally apply selected preset through /candidates/filter/apply
  -> local filter/search/sort helpers
  -> CandidateGrid
  -> CandidateDetailDrawer
  -> bulk status update API
```

## State Boundaries

- `filters`: current toolbar input.
- `appliedFilters`: API-backed filters for `/candidates`.
- `candidates`: loaded candidate records.
- `selectedIds`: bulk selection state.
- `detailCandidate`: drawer state.
- `loading/error/mutating`: request state.

## API Contracts Used

- `GET /candidates`
- `GET /filter-presets`
- `POST /candidates/filter/apply`
- `POST /candidates/bulk-status`

The frontend reads score breakdown and reasons from `VideoCandidate` fields created by the filter/apply step. When an operator selects a preset and clicks Apply, the page applies that preset server-side, persists candidate evaluations, then reloads `/candidates`.

## Why No Heavy State Library Yet

Phase 1 has one operator and one focused screen. React hooks plus pure helper functions are enough and easier to maintain. A cache/store can be added later if the web app grows into multiple coordinated screens.
