# Feature model

All model evidence comes from executable code and the language frontend's syntax
and control-flow analysis. Comments, section headings, and blank-line layout are
excluded from raw facts and features.

The structured model also records code-only access-domain transitions (for example,
`obj.source` to `obj.detector`), terminal control flow immediately before a boundary,
and transitions among resolved calls, external or unresolved calls, indirect calls,
and indexing.

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

The formal model learns feature contributions jointly with module quality and cut
penalty through Structured Energy and Soft-DP. Validation and test performance are
reported only against the finalized real-gold corpus.

## Call-site structure

The language-neutral IR records direct, nested, effect-only, command, and multi-output
call sites together with their explicit inputs, outputs, origin, abstraction level,
and resolution reliability. MATLAB supplies only language-specific syntax and a
conservative primitive-function classification; the common core derives five
code-only boundary features:

- standalone call transition;
- artifact handoff between adjacent calls;
- completion of local call setup (the complement of setup crossing a boundary);
- completion of direct call finalization;
- non-primitive call-chain support.

Call-site reliability attenuates those five values and is not itself cut evidence.
Index access is classified separately from calls. A single direct non-primitive call
with a clear interface can receive module-size and orphan-resistance support, while
single primitive, display, simple save, and low-level shaping operations retain the
normal singleton penalty.
