# CodeSeam V2 current implementation map

This document records the implementation at revision `06d8e94`, before V2
behavior is connected. It describes code, not the intended design.

## Runtime path

`service.analyze_file` reads a MATLAB file, invokes `MatlabFrontend`, optionally
applies project call-resolution context, and passes the resulting `ProgramIR` to
`core.analyzer.analyze_program`.

`analyze_program` performs three operations:

1. `core.features.extract_boundaries` builds one `BoundaryAnalysis` for every
   adjacent top-level statement pair.
2. `core.scoring.score_boundaries` computes the normalized weighted V1 score.
3. `core.scoring.select_recommendations` performs hard candidate filtering and
   global max-DP selection.

The CLI and service expose threshold, prominence radius, minimum prominence,
boundary reward and cut penalty. `AnalysisResult.to_dict` is the JSON schema
source. CFG and dependence caches are intentionally omitted from public JSON.

## MATLAB frontend and static facts

- `languages/matlab/frontend.py` uses tree-sitter and produces language-neutral
  `StatementIR` objects with definitions, reads, mutations, calls, resolved and
  unresolved calls, effects, roles, risks, cut constraints and parse reliability.
- `languages/matlab/control_flow.py` creates `ControlFlowGraph`, including
  branch, loop-back, break, continue and return edges.
- `core/flow.py` calculates reaching-definition data edges, postdominators and
  control dependence.
- `core/dependencies.py` exposes symbol occurrence, def-use and projected PDG
  views used by feature and module scoring.
- `languages/matlab/project.py` resolves calls against a scanned MATLAB project.

The frontend already represents `Effect.UNKNOWN`, `OperationRole.UNKNOWN`, and
risk categories, but V1 boundary features do not carry a general reliability
mask and can conflate unavailable observations with empty observations.

## Boundary features (`core/features.py`)

`extract_boundaries` currently combines fact extraction and normalization. It
uses fixed windows of 4 and 12 statements and emits 15 normalized features:

- symbol: variable death/birth and vocabulary shift;
- interface: overall/input/output compactness;
- dependency: local and medium drop, cohesion and target dispersion;
- call/effect set changes;
- structural/control-followup completion and binary task completion.

It also exposes 18 counts in `raw_features`, but these are an unversioned report
dictionary rather than a stable schema. Completion comes from
`completion_frontiers`, which follows at most four statements. Adjacent module
quality is attached to every boundary.

## Completion (`core/completion.py`)

Only compound producers start completion chains. Aggregation, normalization and
shaping statements can extend a chain if more than half their incoming symbols
come from its frontier. The chain is capped at four follow-up statements.
Presence of evidence becomes binary `task_completion` in boundary features.

## Module quality (`core/module_quality.py`)

`evaluate_module` computes internal cohesion, external compactness, symbol
locality, size fitness, finalization completeness and orphan resistance. Six
fixed weights produce one score. Size fitness is piecewise and a one-statement
terminal module receives a hard zero for orphan resistance.

## V1 scoring and Hard-DP (`core/scoring.py`)

Fifteen feature weights are normalized by their total. Legal boundaries are
then reduced to local peaks above score and prominence thresholds. Remaining
candidates enter `_globally_select_candidates`, whose recurrence adds boundary
surplus and interval module value and subtracts a cut penalty. This is the
production Hard-DP, but its energy contains threshold/prominence terms and is
not shared with a differentiable training path.

## Corpus and tuning

- `corpus/generator.py` provides 17 deterministic families. Segment truth is
  established by generators and expanded to all boundaries after parsing.
- `corpus/training.py` separately tunes non-negative normalized feature weights
  through bounded single/pair perturbation and pairwise ranking accuracy.
- `corpus/selection_tuning.py` separately grid-searches threshold, prominence,
  radius, boundary reward and cut penalty against boundary metrics.
- `corpus/structure.py` hashes parsed surface structure to reduce renderer-style
  leakage, but there is no Raw Fact fingerprint coverage sampler.
- `corpus/ablation.py` evaluates V1 feature removal.
- `corpus/real_projects.py` fetches pinned registry entries and isolates parsing.

## Compatibility boundaries for V2

- Preserve `extract_boundaries`, `ScoringConfig`, `analyze_program`,
  `analyze_file`, legacy corpus train/tune commands, and V1 report fields.
- Introduce Raw Facts below `extract_boundaries` first and prove reconstructed
  V1 features are equivalent.
- Add V2 through explicit APIs/configuration; do not silently reinterpret V1
  selection artifacts.
- Keep static analysis free of Torch. Tensor conversion begins only after Raw
  Facts have been produced.
