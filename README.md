# Script Boundary

Deterministic, explainable function-boundary suggestions for long MATLAB scripts.

Script Boundary parses `.m` files with Tree-sitter, lowers them into a
language-neutral IR, builds control-flow and program-dependence graphs, scores every
legal top-level statement boundary, and selects a globally coherent set of suggested
cuts. It does not require MATLAB and does not rewrite source files.

Comments, `%%` sections, blank lines, and formatting are deliberately excluded from
all scoring decisions.

## Status

This is an experimental MATLAB-first release. It supports analysis and suggestions,
not automatic extraction. The core IR and graph algorithms are language-neutral so
additional Tree-sitter frontends can be added later.

## Installation

Python 3.11 or newer is required.

```bash
pip install .
```

For development with [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
```

## Usage

Analyze a single script:

```bash
script-boundary analyze path/to/script.m
script-boundary analyze path/to/script.m --json analysis.json
```

Explain a legal boundary:

```bash
script-boundary explain path/to/script.m --after-line 120
```

Build project context so external and local MATLAB calls can be resolved:

```bash
script-boundary project-scan path/to/project --json project-index.json
script-boundary analyze path/to/project/script.m --project-index project-index.json
```

The JSON report includes scores, normalized and raw features, dependency crossings,
module quality, constraints, risks, prominence, and selection reasons.

## Reproducible corpus workflow

Generated and downloaded corpora are intentionally not committed.

```bash
script-boundary corpus generate corpus/generated --count 340 --seed 1729
script-boundary corpus audit corpus/generated
script-boundary corpus evaluate corpus/generated --split test
script-boundary corpus train corpus/generated --artifact weights/generated.json
script-boundary corpus tune-selection corpus/generated \
  --weights weights/generated.json --artifact weights/selection.json
```

The real-project registry contains full commit SHAs and license metadata. Downloads
remain local:

```bash
script-boundary corpus registry corpus/real-projects.json
script-boundary corpus fetch-real corpus/real-projects.json corpus/real-downloaded
```

## Architecture

- `languages/matlab` owns MATLAB grammar and semantic adaptation.
- `core` contains language-neutral IR, CFG/PDG analysis, features, module quality,
  scoring, and global dynamic-programming selection.
- `corpus` contains reproducible generation, labeling, evaluation, training, and
  licensed real-project acquisition tools.
- Comments and source layout never enter semantic features.
- Hard extraction hazards are constraints; uncertainty is reported as risk.

See [Architecture](docs/ARCHITECTURE.md), [Features](docs/FEATURES.md),
[Selection](docs/SELECTION.md), and [Corpus](docs/CORPUS.md).

## Validation

```bash
uv run pytest
uv run ruff check src tests
uv build
```

Synthetic metrics are regression diagnostics, not a production accuracy claim.
Real-project model annotations are kept separate from training until independently
reviewed.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports should include the smallest
comment-free executable example that reproduces the behavior when possible.

## License

MIT. See [LICENSE](LICENSE). Third-party repositories listed in the corpus registry
are not redistributed by this repository and retain their own licenses.
