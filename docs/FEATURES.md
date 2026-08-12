# Feature model

Boundary feature schema `boundary-features-v6` stores two representations:

- normalized desirability values used by the linear score;
- raw counts used for explanations, auditing, and future normalization changes.

The expanded set adds directional interface compactness, dependency-target
dispersion, left/right local cohesion support, call-set change,
effect-set change, and control-followup completion. A compound statement receives
a structural-completion reward only after discounting immediate dependencies into
nearby finalization statements.

Dependency-target dispersion distinguishes two superficially similar cases. Several
crossing values feeding distinct downstream statements can form an explicit module
interface, while several intermediates converging immediately into one next
statement usually indicate an unfinished phase.

`dependency_drop` is the sole normalized crossing-edge ratio. The former
`cross_dependency_sparsity` duplicate was removed. Target dispersion is the number
of distinct downstream target statements divided by crossing edges and is therefore
bounded to `[0, 1]`.

Version 4 computes dependency retention consistently inside each window and adds a
12-statement medium-scale measurement alongside the four-statement local value.
This prevents a global crossing edge from being divided by an unrelated local edge
count and reduces sensitivity to small changes inside long phases.

MATLAB call-set features use confirmed built-ins and project functions. Names already
defined as variables are classified as indexes; remaining names stay unresolved and
do not silently become confirmed calls.

Version 5 adds a conservative task-completion feature. A compound control region is
treated as unfinished when its output feeds a short, dependency-dominant chain of
aggregation, normalization, or shaping statements. This is soft evidence, not a hard
constraint, and the chain tracks only the compound node and absorbed follow-up nodes.

Version 6 projects the CFG-derived PDG back onto top-level statements. Dependency
features and task-completion chains therefore retain alternative reaching definitions
across branches and loop exits. Module cohesion also includes discounted control
dependence inside compound statements; nested flow nodes do not become cut positions.

## Module quality

Candidate intervals expose:

- internal cohesion;
- external interface compactness;
- symbol locality;
- size fitness;
- finalization completeness;
- orphan-statement resistance.

These scores are attached to each boundary's adjacent windows for diagnostics and are
evaluated over arbitrary intervals during global cut selection. Proposed modules below
the quality floor pay a deficit cost independently of interval length.

## Current synthetic ablation

On family-held-out adversarial generators, the expanded set still corrects the false
peak after an unfinished loop reduction. It no longer forces a win on the synthetic
large-interface family after removal of an unbounded feature; that case remains an
explicit known weakness rather than a manufactured success. Synthetic regression
results are not evidence of real-project accuracy.
