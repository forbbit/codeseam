# Current Status

Updated: 2026-08-13

## What is finalized

- The architecture is language-neutral from `ProgramIR` onward. MATLAB is the first
  frontend and renderer plugin; Python, C/C++, Java, and JavaScript can be added without
  language branches in the shared core.
- The shared pipeline is ProgramIR -> Semantic Analyzer -> Raw Facts/Reliability ->
  20 continuous boundary features -> Structured Energy -> Soft-DP/Hard-DP.
- CallSite structure and function-sized module-quality rules are implemented.
- Comments, section headings, blank lines, and formatting are excluded from evidence.
- The only supervised corpus is the reviewed real Gold under `corpus/real-curation`.

## Dataset

- 118 MATLAB files from 40 pinned projects.
- 694 extractable-function modules and 576 preferred statement-index cuts.
- Project-isolated split: 82 train / 18 validation / 18 re-sealed test files.
- Split detail: train 487 modules/405 cuts; validation 103/85; test 104/86.
- Dataset audit SHA-256:
  `eed2235518fd7d5058079f5f343e98d4527432f5b6aa1ba9ffae2454fca77f6b`.
- Generated, unreviewed GitHub, and model-produced labels are rejected by the formal
  training loader.

## Analyzer finding

The train/validation-only gap audit found that incomplete call resolution and CallSite
reliability are associated with substantially more false positives. Unknown operation
roles affect almost all validation boundaries, making the role feature weak. The
current validation set contains no switch/try or dynamic-workspace region, so those
known limitations are not the present benchmark bottleneck. Program slicing remains
the leading untested improvement for module completeness and undercutting.

## Training state

- No model is valid for the finalized Gold and current 20-feature schema.
- Older incompatible weights and exploratory training artifacts were deleted.
- The test split is sealed and must not participate in training, feature choices,
  threshold selection, or hyperparameter tuning.
- The next optimization run should occur only after the Analyzer priorities above are
  either implemented or explicitly deferred.

## Verification baseline

- Real-Gold audit passes with zero errors.
- 76 automated tests pass.
- Ruff static checks pass.

Supporting reports retained in `reports`:

- `REAL_GOLD_AUDIT.*`
- `GOLD_FUNCTION_ENCAPSULATION_AUDIT.md`
- `ANALYZER_GAP_CORRELATION.md`
