# CodeSeam V2 baseline freeze

Baseline captured before the V2 implementation began.

- Git revision: `06d8e94` (`main`)
- Python: repository `.venv`
- Test result: `46 passed in 7.91s`
- CLI commands: `analyze`, `explain`, `project-scan`, `corpus`
- Feature artifact: `weights/boundary-v6-v13.json`
- Selection artifact: `weights/selection-v6-v13.json`
- Public analysis schema: the dictionary returned by `AnalysisResult.to_dict()`
- Compatibility fixture: `tests/fixtures/matlab/two_phases.m`

## Frozen synthetic baseline

The deterministic V1 generator was run with `count=40` and `seed=1729`, then
evaluated with `selection-v6-v13.json`.

| Metric | Value |
|---|---:|
| Samples | 40 |
| Labeled boundaries | 350 |
| Pairwise accuracy | 0.749206 |
| Strict exact precision | 0.527778 |
| Strict exact recall | 0.441860 |
| Strict exact F1 | 0.481013 |
| Strict tolerant F1 | 0.594595 |
| Forbidden recommendation rate | 0.0 |
| Recommendations/sample | 0.9 |
| Unique semantic structures | 17 |

For `two_phases.m`, V1 recommends boundaries after source lines 3, 5 and 8.
The V2 implementation must not change these results when invoked through the
legacy path.

## Frozen V1 behavior

V1 computes 15 normalized boundary features, combines them with normalized
fixed weights, applies local-peak, score-threshold and prominence filters, and
then runs a module-quality-aware max dynamic program. Training and selection
are tuned separately by deterministic grid searches.

V2 is additive and versioned. This baseline remains the regression oracle for
the legacy API, CLI defaults and JSON report.
