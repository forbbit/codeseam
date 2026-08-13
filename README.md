# CodeSeam

CodeSeam finds coherent function boundaries in long scripts. MATLAB is the first
language frontend; the semantic core and structured model are language-neutral.

## Current pipeline

```text
Language Frontend / Adapter
  -> Common ProgramIR
  -> Common Semantic Analyzer
  -> Common Raw Facts and Reliability
  -> Common Continuous Features
  -> Structured Energy
  -> Soft-DP training / Hard-DP inference
```

The current supervised dataset is `corpus/real-curation`: 118 reviewed MATLAB files
from 40 projects, split by project into 82 train, 18 validation, and 18 sealed test
files. Generated or unreviewed source is not accepted as training truth.

## Analysis

```text
codeseam analyze path/to/script.m
codeseam analyze path/to/script.m --json analysis.json
codeseam explain path/to/script.m --after-line 120
```

Optional project indexing identifies ordinary external MATLAB calls without analyzing
their function bodies:

```text
codeseam project-scan path/to/project --json project-index.json
codeseam analyze path/to/project/script.m --project-index project-index.json
```

CodeSeam performs static analysis only. It does not execute MATLAB or rewrite source.
Dynamic workspace operations such as `eval` and `assignin` remain constrained risks.

## Dataset audit and formal training

```text
codeseam corpus audit-real-gold corpus/real-curation \
  --json reports/REAL_GOLD_AUDIT.json

codeseam corpus train-formal corpus/real-curation \
  --artifact weights/formal-model.json --device cuda
```

`train-formal` updates parameters from train only, selects the best epoch by validation
exact F1, tolerance-1 F1, then normalized Structured NLL, records complete provenance,
and never loads test. Once the model is frozen, the sealed test can be opened once:

```text
codeseam corpus open-sealed-test corpus/real-curation \
  --artifact weights/formal-model.json \
  --report reports/FORMAL_TEST.json
```

The first optimization experiments predated the finalized Gold and current 20-feature
schema. Their incompatible artifacts have been removed; the next run will be the first
formal training session on the current dataset identity.

## Architecture and development

- `src/codeseam/languages`: language plugins; MATLAB frontend and optional renderer
- `src/codeseam/core`: ProgramIR analysis, raw facts, features, Structured Energy and DP
- `src/codeseam/semantic`: language-neutral SemanticTaskGraph
- `src/codeseam/training`: real-gold loader and sealed formal training protocol
- `src/codeseam/evaluation`: gold audit and formal metrics

See `docs/ARCHITECTURE.md`, `docs/FEATURES.md`, `docs/CORPUS.md`, and
`docs/FORMAL_TRAINING_PROTOCOL.md`.

Run verification with:

```text
uv run pytest
uv run ruff check .
```

## License

CodeSeam is MIT licensed. Curated third-party source retains its original license and
immutable provenance under `corpus/real-curation`.
