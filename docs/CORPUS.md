# Finalized Real-Gold Corpus

`corpus/real-curation` is the only supervised dataset accepted by the formal
training pipeline.

- 118 reviewed MATLAB files from 40 pinned projects
- 694 coherent extractable-function modules
- 576 preferred statement-index cuts
- project-isolated split: 82 train / 18 validation / 18 sealed test files
- immutable source hashes and repository revisions
- high-confidence, user-adjudicated labels

Physical source lines are presentation metadata. Training truth is keyed by
executable-region statement index because MATLAB can contain multiple statements on
one line and compound statements can span multiple lines.

Before training, run:

```text
codeseam corpus audit-real-gold corpus/real-curation \
  --json reports/REAL_GOLD_AUDIT.json
```

Generated code, unreviewed GitHub files, analyzer predictions, and model predictions
are not valid training truth. Formal training is described in
`docs/FORMAL_TRAINING_PROTOCOL.md`.
