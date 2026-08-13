# CodeSeam V2 implementation report

## Outcome

CodeSeam now has a versioned V2 path based on static Raw Facts, explicit
reliability, fixed continuous feature transforms, differentiable module energy,
Soft-DP structured training and Hard-DP inference over the same energy. The V1
path, CLI defaults, reports, weights and selection policy remain operational.

## Phase delivery

### Phase 0 — Baseline freeze

- Baseline revision, tests, metrics, CLI, schema and fixture behavior are frozen
  in `V2_BASELINE_REPORT.md`.
- The real implementation map is in `V2_CURRENT_IMPLEMENTATION_MAP.md`.

### Phase 1 — Raw Facts

- `BoundaryRawFacts` separates static observations from normalized features.
- Facts cover symbols, interfaces, dependencies and spans, reuse mass, calls,
  effects, roles, completion, constraints, risks and reliability.
- `extract_boundaries` now reconstructs the unchanged V1 fields through a
  legacy adapter. The deterministic 40-sample baseline metrics are identical.

### Phase 2 — Semantic Oracle

- The oracle API represents `CORRECT`, `WRONG` and `UNKNOWN` independently and
  reports known accuracy plus unknown coverage by fact family.
- Parse, call resolution, dependency, role and effect confidence are explicit.
  Dynamic workspace and alias uncertainty reduce confidence rather than turning
  an unavailable fact into zero evidence.

### Phase 3 — Continuous features

The fixed V2 transform family contains symbol lifecycle, vocabulary shift,
interface compactness, dependency drop/mass/long-range coupling, role
transition, call/effect changes, continuous unfinished-work completion and
structural support. Positive shape parameters use softplus. Reliability mixes a
feature with an explicit learned baseline; low confidence is not negative
evidence. Every boundary has a feature/contribution/energy decomposition.

### Phase 4 — Continuous module quality

Module features retain cohesion, compactness, locality, size, finalization and
orphan resistance. Trainable weights and smooth size/orphan shapes replace the
V2 hard decisions. V1 module scoring remains available for reports and
regression.

### Phase 5 — Soft-DP and shared energy

For cuts `C`, the implementation uses:

`E(C) = sum(B_i - cut_penalty) + sum(Q(a,b))`.

Soft-DP computes the partition with stable `torch.logsumexp`; structured NLL is
`log Z - E(C*)`. Hard-DP performs max decoding on the exact same energy object.
Tests cover hand-computable partitions, hard constraints, finite-difference
gradients and lengths 1, 10, 100 and 1000.

### Phase 6 — Unified training

`train-structured` jointly updates feature shapes, reliability baselines,
feature weights, module shapes/weights and cut penalty with Adam. Artifacts have
a single versioned schema and contain configuration, all parameters and metrics.
Legacy `train` and `tune-selection` commands are retained.

### Phase 7 — Semantic data tools

- `SemanticTaskGraph` owns true segmentation before rendering.
- The renderer creates multiple MATLAB surface styles for one semantic graph.
- Counterfactual pairs retain labels while changing vocabulary fingerprints.
- Raw fingerprint, novelty/coverage sampling, factor coverage and contradictory
  label collision reporting are implemented.
- Feature correlations, contribution mass, confidence and family ablation
  diagnostics are available.

### Phase 8 — Real corpus validation

The pinned registry was partially fetched before the network operation reached
its time limit. All 227 locally obtained `.m` files were evaluated in isolated
processes so a parser-native failure could not terminate the batch:

| Item | Count |
|---|---:|
| Files found | 227 |
| Files parsed | 206 |
| Isolated failures | 21 |
| Regions | 270 |
| Raw boundaries | 3423 |
| Frontend diagnostics | 76 |
| Low parse-confidence boundaries | 143 |
| Low dependency-confidence boundaries | 2963 |
| Dynamic-workspace boundaries | 67 |

No human-adjudicated real segmentation labels are present, so these results are
frontend/coverage validation, not a claim of real-project cut F1.

## Regression and initial V2 metrics

- V1: 40 samples, strict exact F1 `0.481013`, tolerant F1 `0.594595`, pairwise
  accuracy `0.749206`, forbidden rate `0.0`; all values match the frozen run.
- A three-epoch integration run reduced train NLL from `5.360082` to `5.124866`.
  Every intended parameter family received a finite nonzero gradient.
- The deliberately short initial V2 run overcuts: test F1 `0.341463`, precision
  `0.205882`, recall `1.0`, average cut-count error `5.4`. This is recorded as a
  calibration/data-coverage issue, not hidden with a hard threshold.
- A 30-epoch diagnostic run reduced train NLL to `3.224696` and validation NLL
  to `3.532236`, but its held-out Hard-DP prediction collapsed to no cuts (test
  F1 `0.0`, average cut-count error `1.4`). Together, the short and longer runs
  show that optimization works but the small legacy corpus does not yet identify
  a calibrated structured model. The next model-quality step is semantic factor
  coverage and independently labelled real examples, not a new hard threshold.

## API and compatibility

New principal APIs include `extract_raw_facts`, `ContinuousFeatureModel`,
`StructuredScorer`, `log_partition`, `structured_nll`, `best_segmentation`,
`train_structured`, `SemanticTaskGraph`, `render_matlab`, fingerprint coverage
and semantic oracle evaluation.

Legacy APIs are retained unchanged: `extract_boundaries`, `ScoringConfig`,
`analyze_program`, `analyze_file`, legacy corpus weight tuning and selection
tuning. There is no intentional breaking change. Torch is an optional
`structured` dependency and is imported lazily from CLI V2 commands.

## Known limitations

- The controlled semantic renderer is an extensible first implementation, not a
  complete MATLAB semantic synthesizer for every factor combination.
- Real-project segmentation quality awaits independent human annotations.
- One observed large nested source (`rsHRF.m`) can trigger an access violation in
  the upstream tree-sitter MATLAB native parser/wrapper. Batch tooling isolates
  such files and records UNKNOWN/failure rather than treating them as zero facts.
- Spearman, mutual information and effective-rank reports are not computed in
  the dependency-light runtime; Pearson, contribution and family ablation
  diagnostics are implemented.

## Acceptance checklist

- [x] Raw Facts and Features separated
- [x] Static analyzer remains non-autograd
- [x] Fixed differentiable feature formulas; only numbers train
- [x] Continuous completion and role transition
- [x] Dependency mass and long-range coupling
- [x] Explicit reliability/confidence
- [x] No threshold or hard prominence in V2 training
- [x] Continuous module quality and unified segment energy
- [x] Soft-DP, Hard-DP and structured NLL share parameters
- [x] Autograd/finite-difference checks pass
- [x] Semantic oracle infrastructure
- [x] Semantic task graph, renderer and counterfactuals
- [x] Fingerprint coverage and collision report
- [x] Semantic-family split retained; V1 path and comparison report retained
- [x] Core formulas and artifact parameters documented
