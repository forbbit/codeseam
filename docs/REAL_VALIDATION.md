# Real-project validation

Synthetic samples are useful for exact source maps and controlled hard negatives,
but they cannot establish real-world quality. Real MATLAB repositories are a
separate validation layer and are not used to fit initial weights.

`corpus/real-projects.json` contains reviewed repository metadata only, never third-party
source. Each entry has an HTTPS URL, full 40-character commit SHA, SPDX license
identifier, license-file path, and selection globs. Fetching is an explicit network
operation; ordinary tests and analysis never download code.

The fetcher obtains files from the exact commit and records:

- repository and immutable revision;
- SPDX license and license-file hash;
- selected `.m` paths and SHA-256 hashes;
- parser diagnostics and executable-region counts.

Downloaded source is ignored by Git. Whether source may be redistributed is a
separate decision from whether it may be used locally for validation.

## Human annotation

An annotation template enumerates every legal boundary as `neutral`. Reviewers
must classify all boundaries using the five-level label set. Every non-neutral
label requires a reason. The annotation is tied to the exact source SHA-256.

For a formal validation set, two reviewers should annotate independently. The
agreement command reports exact five-level agreement and cut-versus-noncut
agreement. Disagreements should be adjudicated into a third file while preserving
the two original annotations.

Function definitions and comment sections are not automatic ground truth. Human
review must judge whether a continuous block is a meaningful extraction boundary,
including control flow, workspace behavior, and external dependencies.
