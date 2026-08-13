# Curation status

This is the finalized curated-real gold dataset. Dataset publication did not
start formal model training.

- Candidate batch: 50 pinned GitHub projects, 200 MATLAB files.
- Parser-clean at acquisition: 200/200; 11 were later rejected because the
  annotation render was unstable or collapsed a semantic block too coarsely.
- Contains a single executable region with at least 30 statements: 200/200.
- Long top-level scripts: 29/200; the remaining candidates contain long functions.
- Automatically pre-flagged for content review: 24/200.
- Blind decisions completed: 200/200.
  - Candidates with semantic module partitions: 118 after the final audit.
  - File status `ACCEPT`: 118 expert-final candidates (all boundaries
    high-confidence).
  - File status `REVIEW`: 0.
  - Rejected: 80 (including plotting/GUI utilities, exploratory or repetitive
    scripts, near-duplicates, and annotation-time parser failures).
  - Accepted regions: 118; extractable-function modules: 694.
  - Granularity audit: all 118 accepted files rechecked using extractable-function
    completeness; 45 over-fragmented module boundaries were removed.
- User adjudications completed: 10/10.
- Dataset split: 82 train / 18 validation / 18 test.
- Test Gold was audited under the unified function-encapsulation rule before
  retraining and then re-sealed.
- Project isolation: 22 train / 9 validation / 9 test projects; no overlap.
- Trainable real gold records published: 118.
- Formal training started: no.

The 80 rejected candidates, blind-review copies, dossiers, downloaded repositories,
and private acquisition indexes were deleted after the accepted source hashes and
license notices were verified in the published dataset.
