# Gold Function-Encapsulation Audit

The 118-file curated corpus was rechecked against one unified objective: every segment
should be reusable as an existing function call or extractable as a coherent new
function. The review used executable syntax, call sites, data flow, and segment
interfaces only; comments were not used as model evidence.

Rules applied:

- keep local setup, core execution, and direct finalization in one module;
- allow an already encapsulated high-level call to form a one-statement module;
- do not isolate low-level primitives, formatting, logging, or parameter preparation;
- preserve a complete top-level loop, conditional, or switch when it performs one task;
- prefer fewer modules when two partitions are equally reusable.

All train, validation, and test records were structurally screened and manually
reviewed as a one-time annotation-standard migration before retraining. Six training
records required revision:

- `M0008`: separated nonlinear registration, annotation transformation, persistence,
  and transform inversion where existing high-level functions already encapsulate them;
- `M0049`: separated tunable-parameter processing, companion-file generation, and code
  patching;
- `M0066`: separated design persistence, duration practice, and main experiment execution;
- `M0136`: separated independently reusable NIRS import, correction, conversion,
  filtering, averaging, and inspection stages;
- `M0175`: merged a one-assignment `sform` module back into unit normalization;
- `M0188`: separated network construction from validation-set construction.

Two test records required revision under the same rule:

- `M0119`: moved result-store initialization into the simulation-and-persistence
  module instead of attaching it to path and horizon setup;
- `M0125`: separated scene serialization, viewer launch, and simulator execution into
  complete function-sized operations.

The other 16 test records were reviewed and retained unchanged. The test Gold is now
re-sealed: subsequent model training, feature decisions, threshold selection, and
hyperparameter tuning must use train and validation only.

Corpus totals changed from 679 modules and 561 preferred cuts to 694 modules and 576
preferred cuts. Source files, project-isolated splits, licenses, and source hashes did
not change. The post-audit dataset SHA-256 is
`eed2235518fd7d5058079f5f343e98d4527432f5b6aa1ba9ffae2454fca77f6b`.
