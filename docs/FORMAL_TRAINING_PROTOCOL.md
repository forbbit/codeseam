# Formal Structured Training Protocol

Status: infrastructure implemented; the first formal optimization run has not started.

## Isolation contract

- `train` is the only split allowed to update parameters.
- `validation` selects the best epoch lexicographically by exact boundary F1, then
  tolerance-1 F1, then normalized Structured NLL. This prevents a lower loss from
  replacing a checkpoint whose discrete cuts are more accurate.
- Optimization uses deterministic shuffled file mini-batches. Structured NLL is divided by
  each region's legal-boundary count before gradient aggregation, so long files do not
  dominate parameter updates. Raw NLL remains in the history for diagnosis.
- Early stopping cannot activate before the configured minimum epoch.
- A class-balanced boundary BCE is used as an auxiliary training signal alongside
  Structured NLL. It prevents the highly imbalanced boundary set from collapsing to
  all-no-cut; Soft-DP remains the structured objective and Hard-DP remains inference only.
- Learning-rate and balanced-boundary-weight schedules are supported, with an independent
  50-epoch horizon. They are constant by default (`0.01` and `0.5`): a controlled
  comparison found the decaying configuration slightly worse on both exact and
  tolerance-1 F1.
- `test` is not parsed or loaded by `train-formal`.
- Projects must occur in exactly one split and must match `split_projects.json`.
- The manifest and project split file are hashed together. Test evaluation refuses a model if
  that hash has changed.
- A frozen model artifact can open the test split once. A sidecar receipt records the report
  path and hash; changing the report filename does not permit a second evaluation.

## Formal model artifact

The artifact records the dataset hash, exact sample and project membership of all splits,
random seed, training configuration, feature and energy schema versions, source commit,
validation history, best epoch, validation metrics, and frozen model parameters. Its
`test_status` remains `sealed_not_loaded` after training.

## Metrics

Validation and test reporting includes exact boundary precision/recall/F1, tolerance ±1 and
±2 statement F1, exact segmentation accuracy, overcut and undercut rates, average cut-count
error, hard-constraint violations, project macro averages, script/function strata, and
statement-count length buckets.

## Commands

The following command starts a real optimization run and therefore must be invoked only after
review of the configuration:

```text
codeseam corpus train-formal corpus/real-curation \
  --artifact weights/formal-model.json --device cuda
```

After the model and validation result have been frozen, the test set can be opened once:

```text
codeseam corpus open-sealed-test corpus/real-curation \
  --artifact weights/formal-model.json --report reports/FORMAL_TEST.json
```

There is no alternate unsealed training command. `train-formal` is the only supported
optimization entry point.
