# Resume — Compare Failing vs Passing aweme Trace

## Scope lock

Live comparison diagnosis only:
- compare 1 passing aweme vs 2 failing aweme
- identify first divergence stage for posted/duration/counts
- no broad refactor/fix/redesign

## Selected IDs

- passing_aweme_id: `7489123456789012345`
- failing_aweme_id_1: `7489123456789012346`
- failing_aweme_id_2: `7489123456789012347`

## Execution order

1. docs-first init (done)
2. document passing baseline A→F (done)
3. trace failing item 1 A→F (blocked: missing concrete evidence)
4. trace failing item 2 A→F (blocked: missing concrete evidence)
5. build divergence tables (posted/duration/counts) (partial)
6. classify each failing item + name first divergence stage (currently `unknown` for both fails)
7. identify single narrowest next fix boundary (prepared)
8. finalize verification summary (approved with evidence-missing status)

## Current status

Passing baseline is concrete. Both failing IDs remain explicitly evidence-missing/unknown per latest approval due placeholder-only inputs. Existing one-shot diagnostics plumbing is available, but no concrete fail-item output JSON was provided in this run.
