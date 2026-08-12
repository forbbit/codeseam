# CodeSeam project handoff

Last updated: 2026-08-12

Repository: <https://github.com/forbbit/codeseam>

Local checkout: `D:\rzhfan\codeseam`

Default branch: `main`

This document is the starting context for a new development conversation. The
current code and this document take precedence over the two early prototype/spec
files discussed before the repository was rebuilt.

## 1. Product goal

CodeSeam analyzes a long script and recommends natural boundaries where continuous
code can later be extracted into function modules. It should identify the completion
of one task and the beginning of another while avoiding fragmented, locally plausible
but globally poor cuts.

The current release analyzes MATLAB `.m` scripts. The long-term product is
multi-language, but language support must be added through adapters rather than by
putting language-specific rules into the core algorithm.

Current scope:

- Analyze every legal top-level statement boundary.
- Rank and globally select a coherent set of recommended seams.
- Explain scores, data dependencies, constraints, risks, and adjacent-module quality.
- Optionally scan a MATLAB project to resolve local and external `.m` function calls.
- Produce console and JSON reports.
- Never execute MATLAB code.
- Never rewrite or split source files yet.

## 2. Decisions that must be preserved

1. **MATLAB first.** Python source analysis is not currently implemented.
2. **Tree-sitter for every language.** Python's built-in AST is not an implementation
   reference and should not be reintroduced as a special core dependency.
3. **Language-neutral core.** MATLAB grammar node names and semantic rules belong
   only in `src/codeseam/languages/matlab`. Future languages emit the same IR facts.
4. **Comments must not influence boundaries.** Comments, `%%` sections, blank lines,
   indentation, and formatting are excluded from features and selection. Misleading
   user comments must not lower accuracy. This invariance has an automated test.
5. **Suggestion before rewriting.** The present goal is accurate boundary advice,
   not automatic function extraction. Extraction comes only after interfaces and
   safety are sufficiently validated.
6. **Global partition quality matters more than more features.** The main historical
   problem was excessive local cuts. Selection now uses dynamic programming and
   module quality instead of a fixed minimum-distance suppression rule.
7. **No repeated-task model is needed.** Each input script is an independent unit;
   do not assume the same task repeats inside one script.
8. **Synthetic labels are regression evidence, not real-world truth.** Generated
   data may train/calibrate weights, but public accuracy claims require independently
   annotated real MATLAB projects.
9. **Early files were references only.** Do not restore code or architecture merely
   because it appeared in `Script_Boundary_Scoring_Codex_Spec.md` or
   `ScriptBoundaryPrototype.zip`; later conversation decisions superseded them.
10. **Python is the temporary implementation language.** A later Rust port is
    acceptable for performance, but it should preserve the IR and adapter boundary.

## 3. Current pipeline

```text
MATLAB .m source
  -> Tree-sitter runtime
  -> MATLAB syntax and semantic frontend
  -> language-neutral ProgramIR
  -> executable regions and legal top-level boundaries
  -> fine-grained CFG
  -> reaching definitions + control dependence -> first PDG
  -> dependency/lifetime/completion evidence
  -> normalized boundary features + raw diagnostics
  -> weighted boundary score
  -> local-peak and prominence candidate filtering
  -> constraints and risks
  -> arbitrary-interval module-quality evaluation
  -> region-level dynamic-programming selector
  -> console or JSON recommendations
```

Script code and each local function body become separate executable regions.
Existing function declarations are not treated as statements in the surrounding
script region.

## 4. What the algorithm currently models

### Intermediate representation

Statements expose source ranges, definitions, reads, mutations, confirmed and
ambiguous calls, effects, control effects, risks, and parse reliability. The core
does not import Tree-sitter or MATLAB modules.

### CFG and PDG slice

The frontend lowers sequential flow, `if`/`elseif`/`else`, `for`, `parfor`, `while`,
`break`, `continue`, and `return`. Core fixed-point analysis computes reaching
definitions across branch alternatives and loop back edges. Post-dominators produce
control-dependence edges, which combine with data dependence into the current PDG.

This is not yet a complete MATLAB CFG/PDG. Missing areas include `switch`,
`try`/`catch`, exceptional flow, short-circuit expression flow, aliases, dynamic
workspace behavior, classes/packages/path precedence, and general program slicing.

### Feature schema

The frozen schema is `boundary-features-v6`. It includes:

- variable death and birth;
- interface compactness;
- local and medium dependency drop;
- vocabulary shift;
- structural completion;
- directional input/output interface compactness;
- local cohesion support;
- call-set and effect-set change;
- control-followup completion;
- dependency-target dispersion;
- task completion.

Normalized feature values drive the score. Raw counts are retained for explanations,
auditing, and future normalization changes. Formulas and rationale are documented in
[`FEATURES.md`](FEATURES.md).

### Completion evidence

The first completion-closure layer begins at compound top-level statements and
follows path-sensitive def-use edges through at most four aggregation,
normalization, or shaping statements. It is deliberately soft evidence: a loop or
branch is not considered complete merely because its `end` token was reached when
immediate dependent finalization work remains.

### Constraints and risks

Features are desirability evidence. Constraints prohibit selection. Risks expose
uncertainty without silently changing the score. Examples include parser problems,
unsafe extraction conditions, call-versus-index ambiguity, and workspace behavior.

## 5. Global selection

Scoring and recommendation selection are separate. Every legal boundary receives a
score; only some become recommendations.

Current selector defaults:

| Parameter | Value |
| --- | ---: |
| Score threshold | `0.58` |
| Minimum prominence | `0.055` |
| Prominence radius | `5` boundaries |
| Boundary reward weight | `0.85` |
| Cut penalty | `0.03` |
| Module-quality floor | `0.60` |
| Module-deficit penalty | `0.20` |

Selection proceeds by candidate peak/prominence filtering, constraint rejection,
and region-level dynamic programming. The objective balances seam evidence against
the quality of every interval created by the selected cut set. Module quality uses
internal cohesion, external coupling/interface compactness, symbol locality, size
fitness, finalization completeness, and orphan resistance.

Interval quality is length weighted, but a separate unweighted deficit penalty is
charged when any proposed module falls below the quality floor. This replaced fixed
distance suppression and was introduced to stop one- or two-statement fragments
from hiding inside a good average score.

Frozen artifacts:

- `weights/boundary-v6-v13.json`
- `weights/selection-v6-v13.json`

## 6. Corpus and evaluation

The deterministic generator currently covers 17 structural families, including:

- linear and composed pipelines;
- loops followed by finalization;
- branches and branch merges;
- nested control structures and state-like flow;
- mixed scripts and local functions;
- project/external function calls and function handles;
- workspace effects;
- large interfaces;
- adversarial nearby or false peaks.

Structural fingerprints prevent equivalent structures from crossing train,
validation, and test splits. Generated sources and downloaded third-party code are
ignored by Git and can be recreated.

Frozen v0.1 synthetic regression result (`340` generated scripts, seed `1729`):

| Measurement | Result |
| --- | ---: |
| Held-out test scripts | 100 |
| Unique held-out structures | 5 |
| Labeled legal boundaries | 900 |
| Strict precision | 0.667 |
| Strict recall | 0.667 |
| Strict F1 | 0.667 |
| Structure-macro F1 | 0.600 |
| Forbidden recommendation rate | 0.000 |
| Excess-cut rate | 0.000 |
| Recommendations per script | 1.20 |

These metrics reveal meaningful remaining error and must not be described as
production or real-project accuracy. Reproduction commands and limitations are in
[`BENCHMARKS.md`](BENCHMARKS.md).

The real-project registry pins four permissively licensed repositories by full
commit SHA in `corpus/real-projects.json`. Third-party source is fetched explicitly,
kept local, and never committed. The annotation tools support complete legal-boundary
templates, validation, two-reviewer agreement, and later adjudication.

## 7. Important empirical history

- The real user script
  `F:\4_USTB\1_LongitudinalPowerMonitoring\4_PKU_EXP\pku_experiment\RX_DPqam.m`
  was repeatedly used as a qualitative over-segmentation check.
- The latest remembered selector produced 15 recommended boundaries for that file.
- The user judged the result broadly useful: a few false cuts remained, but there
  were few or no obvious missed cuts.
- RX was not treated as labeled ground truth and was not used to claim accuracy.
- On an earlier eight-file weak-supervision diagnostic set, adding the module-deficit
  term reduced predictions from 41 to 32 while retaining 14 exact model-label
  matches. Those labels were model judgments, not human truth, and were not mixed
  into training.

## 8. Repository and commands

Installation/run from GitHub:

```bash
uvx --from git+https://github.com/forbbit/codeseam codeseam analyze file.m
```

Local development:

```bash
cd D:\rzhfan\codeseam
uv sync --extra dev --locked
uv run python -m pytest
uv run ruff check .
uv build
```

Main CLI operations:

```bash
codeseam analyze file.m
codeseam analyze file.m --json analysis.json
codeseam explain file.m --after-line 120
codeseam project-scan matlab-project --json project-index.json
codeseam analyze file.m --project-index project-index.json
```

Corpus workflow:

```bash
codeseam corpus generate corpus/generated --count 340 --seed 1729
codeseam corpus audit corpus/generated
codeseam corpus evaluate corpus/generated --split test \
  --selection-policy weights/selection-v6-v13.json
codeseam corpus train corpus/generated --artifact weights/generated.json
codeseam corpus tune-selection corpus/generated \
  --weights weights/generated.json --artifact weights/selection.json
```

Current automated verification:

- Ruff passes.
- 46 pytest tests pass.
- Wheel and source distribution build successfully.
- GitHub Actions tests Python 3.11, 3.12, and 3.13.
- The first public CI run for commit `b9e18b7` completed successfully.

Windows note: this machine's browser/system HTTPS proxy is `127.0.0.1:7897`, while
Git does not automatically inherit it. If a GitHub push times out on port 443, the
working one-command override was:

```powershell
git -c http.proxy=http://127.0.0.1:7897 `
    -c https.proxy=http://127.0.0.1:7897 push
```

Do not commit proxy settings to the repository.

## 9. Repository structure

```text
.github/                 CI and contribution templates
corpus/real-projects.json pinned real-project metadata only
docs/                    architecture, algorithms, evaluation, roadmap, handoff
examples/                small reproducible MATLAB demo
src/codeseam/core/       language-neutral analysis and selection
src/codeseam/languages/  language adapters; MATLAB is the only frontend today
src/codeseam/corpus/     generation, annotation, metrics, training, calibration
src/codeseam/reporting/  console and JSON rendering
tests/                   46 automated tests and MATLAB fixtures
weights/                 frozen boundary and selection artifacts
```

## 10. Known limitations and technical debt

- Only MATLAB `.m` is supported; `.mlx` is not.
- No automatic extraction or function-signature generation.
- The MATLAB project index does not reproduce MATLAB path precedence, packages,
  private folders, classes, toolboxes, or dynamic dispatch.
- Call-versus-index ambiguity remains conservatively represented.
- CFG/PDG coverage is incomplete as listed above.
- Real-project boundary labels have not yet received independent human review.
- Synthetic structure coverage is broad but still finite, and only five distinct
  structures are in the current held-out test split.
- The selector still has false positives on RX and uneven performance across
  generated families.
- Console output is comprehensive but verbose; a compact view and HTML report are
  still planned.
- The Python package is not yet published to PyPI and there are no standalone
  binaries or tagged GitHub releases.

## 11. Recommended next work

The highest-value next step is real-project validation, not adding more boundary
features or a neural network.

Suggested order:

1. Fetch the four pinned MATLAB projects and select representative long scripts,
   especially mixed script/function files and project-dependent workflows.
2. Create complete legal-boundary annotation templates without showing model output
   to annotators.
3. Obtain two independent human annotations and adjudicate disagreements.
4. Report exact and tolerant precision/recall/F1, forbidden hits, excess cuts,
   recommendations per 100 statements, per-family/file metrics, and inter-annotator
   agreement.
5. Compare false positives with module-quality and task-completion diagnostics;
   improve candidate selection before adding new features.
6. Add a compact default console report and optional HTML visualization.
7. Only after evidence improves, preview extractable function inputs/outputs and
   design opt-in source rewriting.
8. Package a release (PyPI and/or standalone binary), tag it, and add GitHub topics
   and a short launch post/demo.

Neural networks were discussed but intentionally deferred. The current bottleneck is
ground-truth quality and selecting a coherent subset of candidates, not an obvious
lack of nonlinear scoring capacity.

## 12. Files to read first in a new conversation

1. This file: `docs/HANDOFF.md`
2. `README.md`
3. `docs/ARCHITECTURE.md`
4. `docs/FEATURES.md`
5. `docs/SELECTION.md`
6. `docs/BENCHMARKS.md`
7. `docs/REAL_VALIDATION.md`
8. `src/codeseam/core/analyzer.py`
9. `src/codeseam/core/scoring.py`
10. `src/codeseam/languages/matlab/frontend.py`

For the next conversation, a sufficient opening request is:

> Read `D:\rzhfan\codeseam\docs\HANDOFF.md` and continue CodeSeam from the
> recommended next work. Treat the repository and that handoff as the source of
> truth.
