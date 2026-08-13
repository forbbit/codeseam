# Curated real MATLAB gold corpus

This directory is the finalized real-code gold dataset. It contains 118 reviewed
MATLAB files, their semantic-module labels, immutable provenance, project-isolated
splits, and preserved repository license notices.

- `manifest.jsonl`: trainable records, semantic segments, boundary labels, and provenance.
- `sources/`: the 118 accepted source snapshots named only by blind ID.
- `licenses/`: license and notice files preserved from accepted repositories.
- `split_projects.json`: deterministic project-to-split assignment.

Training truth uses the `boundary` statement index in every manifest boundary.
`after_line` is retained for display only and must not be used to reconstruct cuts.
Ordinary unresolved external function calls remain atomic dependencies; their source
implementations are not required. Dynamic shared-workspace operations retain hard
constraints and risks.

## Admission pipeline

1. Discover repositories with a recognized open-source license.
2. Pin the repository to an immutable commit and hash each selected source.
3. Exclude tests, examples, demos, generated/obsolete code, embedded third-party
   copies, license files, and student exercises.
4. Require at least one parser-clean executable region with 30 statements.
5. Blind the repository and path while annotating; CodeSeam predictions and
   scores are not shown to the annotator.
6. Reject near-duplicates and over-represented plotting/glue templates.
7. Mark semantic modules first. `preferred_cut` and `discouraged_cut` labels are
   derived from the accepted module partition.
8. Recheck every accepted partition using extractable-function completeness:
   each module must have a coherent responsibility and explainable inputs and outputs.
9. Apply the unified function-encapsulation audit: keep setup/core/finalization intact,
   allow already encapsulated high-level calls to stand alone, preserve complete compound
   statements, and reject singleton low-level preparation or formatting modules.

Every published record is `curated_real_gold`, `user_adjudicated`, high confidence,
and includes repository, pinned revision, source path, SHA-256, and SPDX license.
The 80 rejected candidates and all temporary acquisition worktrees were removed.

Splits are assigned by repository, not by file, so related files from one project
cannot leak across train, validation, and test. Creating this dataset did not run
formal training.
