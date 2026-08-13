# Architecture

## Processing pipeline

```text
Source file
  -> Language registry
  -> Language Adapter / Frontend (MATLAB is the first plugin)
  -> Common ProgramIR
  -> CommonSemanticAnalyzer (CFG/PDG, Raw Facts, Reliability)
  -> Common Continuous Features
  -> Structured Energy
  -> Soft-DP for formal structured training
  -> Hard-DP for inference
```

## Multi-language ownership

`languages/registry.py` selects a frontend by explicit language ID or registered
extension. A Python, C, C++, Java, or JavaScript plugin owns its grammar, symbol
rules, call resolution, effects, risks, and CFG lowering. It must emit the same
`ProgramIR`; it must not add language branches to `core`.

`core/semantic_analyzer.py` is the shared semantic boundary. It compiles each
`ExecutableRegion` into a language-neutral dependence graph plus boundary raw
facts and reliability. Feature transforms, structured energy, and both DP
implementations consume only shared IR/facts.

`semantic/task_graph.py` owns the language-neutral task representation. Renderers
are plugins under their language packages; MATLAB's first renderer is
`languages/matlab/renderer.py`.

To add a frontend, implement `LanguageFrontend`, register a `FrontendPlugin`, and
add language conformance tests. A future renderer separately implements
`SemanticRenderer`; analysis support does not require a renderer.

## Training boundary

Formal structured training uses the sealed protocol in `FORMAL_TRAINING_PROTOCOL.md`.
Training loaders accept finalized `curated_real_gold` records only when
they carry high-confidence final review plus immutable revision and source hashes.
Unlabeled GitHub or other external sources remain detection-only and are rejected
before parsing or feature extraction. Generated or model-produced labels are not
accepted by the training loader.

Structured truth is keyed by executable-region statement index, never physical line.
MATLAB permits several statements on one line, so source lines are presentation
metadata only. Unannotated local helper regions in an accepted file are skipped rather
than silently interpreted as zero-cut negative examples.

The MATLAB frontend owns all grammar node names and MATLAB semantics. The core
owns no Tree-sitter or MATLAB dependencies. A future language frontend must emit
the same IR facts rather than adding language-specific branches to the core.

## Current IR boundary

Each executable region contains ordered statements. Statements expose:

- definitions, reads, and mutations;
- calls whose call-versus-index meaning may remain ambiguous;
- language-neutral effects and control effects;
- extraction risks;
- source ranges and parse reliability.

Script code and each function body are separate executable regions. Existing
function definitions are declarations, not statements in the surrounding script
region.

The region also carries an internal fine-grained `ControlFlowGraph`. Its flow nodes
map back to their containing top-level statement, so the existing boundary model can
remain stable while graph analyses inspect compound-statement internals. CFG and PDG
types are language-neutral; only the MATLAB lowering layer knows Tree-sitter node names.

## Decision layers

- **Features** are normalized evidence used in a weighted score.
- **Constraints** prohibit a recommendation at a boundary.
- **Risks** report uncertainty or hazards without silently changing the score.

Initial feature weights are experimental constants, not trained values. They are
intentionally isolated in `core/scoring.py` so a future corpus-training pipeline
can produce frozen, versioned weights.

Boundary output keeps normalized desirability values and raw measurements
separately. The v6 set includes directional input/output interfaces, local and
medium-scale dependency retention,
sparsity and target dispersion, left/right local cohesion, call/effect set changes,
and control-followup completion. Structural completion is discounted when a
compound statement's outputs feed immediate finalization statements.

Each boundary also carries diagnostic quality for adjacent candidate modules:
internal cohesion, external coupling, symbol locality, size fitness, finalization
completeness, and orphan-statement resistance. The global selector evaluates these
scores over arbitrary intervals and charges a deficit cost for weak proposed modules.

Candidate selection is a region-level dynamic program. It optimizes the complete
ordered cut set using boundary evidence and every resulting interval's module
quality, rather than accepting candidates greedily or imposing a fixed distance.
Interval quality is length weighted so its total mass remains one, and each selected
cut pays an explicit penalty. A separate quality-deficit term prevents weak short
fragments from becoming almost free under length weighting.

A MATLAB project index can be supplied to analysis. Confirmed project and same-file
local functions then replace ambiguous call/index names in call-set features. The
index is advisory and does not attempt to emulate MATLAB path execution.

The first completion-closure layer is deliberately narrower than the full CFG/PDG. It
starts at compound top-level statements and follows path-sensitive def-use edges through at
most four aggregation, normalization, or shaping statements. The emitted evidence is
soft and explainable. The graph is projected onto legal top-level cut positions.

The first graph slice lowers sequential statements, `if`/`elseif`/`else`, `for`,
`parfor`, and `while`, plus `break`, `continue`, and `return`. Core fixed-point analysis
computes reaching definitions across alternative paths and loop back paths. Core
post-dominator analysis derives control-dependence edges; these are combined with data
dependence into a first program-dependence graph. The graph is currently internal and
is intentionally omitted from the public JSON schema.

## Source-layout invariance

Comments, MATLAB `%%` sections, blank lines, and formatting are excluded from IR
facts and scoring. They may be retained later by a source-preserving rewriter,
but cannot become boundary evidence. Invariance is enforced by automated tests
using deliberately misleading comments.

## Known first-slice limitations

- MATLAB `.m` only; `.mlx` is not supported.
- Project scanning resolves names provided by `.m` files, but MATLAB path precedence,
  packages, classes, private folders, toolboxes, and dynamic dispatch remain unresolved.
- Call versus indexing ambiguity is reported conservatively.
- `switch`, `try`/`catch`, exceptional control flow, short-circuit expression flow,
  alias analysis, and dynamic workspace resolution are not modeled yet.
- The PDG feeds completion closure, dependency features, and module-quality cohesion,
  but general backward/forward program slicing is not implemented yet.
- Scores are experimental; the current release is for architecture and corpus
  iteration rather than automatic source rewriting.
