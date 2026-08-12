# Supervised Corpus

The corpus is generated from explicit program families rather than unconstrained
random source text. Each family owns its ground-truth module transitions and hard
negatives.

Current seed families cover:

- sequential normalization and selection pipelines;
- a complete loop followed by dependent finalization;
- external scripts and workspace injection;
- mixed script code and an existing local function.
- nested branches and loops followed by aggregation;
- multi-output helpers and long-lived shared configuration;
- a deliberately misleading structural peak after a reduction loop;
- a multi-file project using function handles and indirect calls.
- alternative definitions merging after branches;
- loop-carried state with nested conditional updates;
- consecutive conditional post-processing stages;
- nested state-machine control flow;
- held-out multi-file and loop/branch topologies.

Every legal statement boundary is recorded. Labels use five levels:
`preferred_cut`, `acceptable_cut`, `neutral`,
`discouraged_cut`, and `forbidden_cut`. A future training pipeline may optimize
ranking weights against preferred and acceptable cuts, while forbidden cuts remain
language constraints rather than learned penalties.

For generated samples, transitions between declared `segments` are derived as
preferred boundaries and boundaries inside those modules default to discouraged.
Neutral is reserved for genuinely ambiguous hand-authored cases. For evaluation,
neutral predictions are ignored, while predictions on discouraged
or forbidden boundaries count as false positives. Exact matching uses the region and
statement-boundary index, not line number, because MATLAB permits several statements
on one physical line.

The manifest is JSON Lines with schema version, family, deterministic seed,
train/validation/test split, relative path, SHA-256, tags, provenance, and boundary
truth. Generator-family and project grouping must be considered when building
evaluation splits; random file-level splitting is not sufficient for estimating
generalization.

Records can also contain continuous `segments` with module IDs and extraction
safety, plus checksummed `auxiliary_files` for generated projects. This makes the
same corpus usable later for module-quality and project-resolution experiments,
not only binary boundary ranking.

The current generator assigns whole scenario families to one split. No family is
allowed to appear in more than one of train, validation, or test. This is stricter
than content-hash splitting: even distinct parameterizations of the same template
cannot leak into held-out evaluation. A perfect score on synthetic families is
still not evidence of production quality. Frozen weights must not be promoted until
real-project validation exists.

Small generated sets are not guaranteed to populate all three splits. Training
requires a non-empty training split; validation and test metrics are reported only
when those held-out partitions exist.

This generated layer will be complemented by hand-authored minimal fixtures and a
separately licensed real-project validation set. Synthetic scores alone are not a
claim of real-world quality.

Recipe version 3 stores an identifier-independent structural fingerprint for every
sample. Auditing rejects fingerprints that leak across splits. Evaluation reports
both micro metrics and structure-macro metrics so repeated parameterizations of one
template cannot silently dominate the result. The `composed_pipeline` family builds
programs from independently selected acquisition, preparation, analysis, and output
phases, producing varied dependency topology rather than literal-only perturbations.
The v13 corpus contains 340 samples across 17 scenario families: 160 train, 80
validation, and 100 frozen test samples. The test split contains five independent
structural fingerprints.
